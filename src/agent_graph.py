from __future__ import annotations
from typing import Any, TypedDict
from dataclasses import dataclass
from pathlib import Path
import json
from .models import AgentProfile, ToolConnector, PolicyRule, AgentRun, ApprovalRequest, Incident, now_iso, new_id
from .provider_router import ProviderRouter
from .policy import assess_task_risk, infer_intent, plan_tool_calls, policy_check_tool_calls
from .connectors import execute_tool_call
from .database import save_run, save_incident


class AgentOpsState(TypedDict, total=False):
    task: str
    agent: AgentProfile
    connectors: list[ToolConnector]
    policies: list[PolicyRule]
    provider_router: ProviderRouter
    provider_choice: str
    approval_mode: str
    run: AgentRun
    context: str
    db_path: Path | str


@dataclass
class GraphRunResult:
    run: AgentRun
    trace: list[dict[str, Any]]


def _get_db_path(state: AgentOpsState) -> Path:
    if 'db_path' in state and state['db_path']:
        return Path(state['db_path'])
    # Default fallback
    base_dir = Path(__file__).resolve().parent.parent
    return base_dir / 'outputs' / 'agentops_guard.db'


def _log(state: AgentOpsState, node: str, action: str, **details: Any) -> None:
    event = {'time': now_iso(), 'node': node, 'action': action, **details}
    state['run'].audit_log.append(event)


def _receive_task(state: AgentOpsState) -> AgentOpsState:
    agent = state['agent']
    state['run'] = AgentRun(
        agent_id=agent.agent_id,
        agent_name=agent.name,
        task=state['task'],
        provider=state.get('provider_choice', 'auto'),
        status='planned'
    )
    _log(state, 'receive_task', 'created_agent_run', agent=agent.name)
    save_run(_get_db_path(state), state['run'])
    return state


def _classify_intent(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    run.intent = infer_intent(run.task)
    _log(state, 'classify_intent', 'classified_task_intent', intent=run.intent)
    save_run(_get_db_path(state), run)
    return state


def _retrieve_context(state: AgentOpsState) -> AgentOpsState:
    agent = state['agent']
    enabled = ', '.join([(c.real_connector or c.tool_name) for c in state['connectors'] if c.enabled])
    state['context'] = f"Agent: {agent.name}\nOwner: {agent.owner}\nAllowed tools: {', '.join(agent.allowed_tools)}\nEnabled connectors: {enabled}\nWorkspace: secure connector registry with persistent SQLite audit trails."
    _log(state, 'retrieve_context', 'assembled_workspace_context', allowed_tool_count=len(agent.allowed_tools))
    save_run(_get_db_path(state), state['run'])
    return state


def _plan_actions(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    router = state['provider_router']
    prompt = f"""
    Task:
    {run.task}

    Context:
    {state.get('context', '')}

    Analyze the user instruction and return a structured tool routing plan. List any tools you wish to invoke.
    """
    model_result = router.generate(
        prompt, 
        system='You are an AI agent governance control tower. Plan safe tool actions only. Never bypass approval.', 
        provider=state.get('provider_choice', 'auto')
    )
    run.provider = model_result.provider
    run.model = model_result.model
    run.latency_ms += model_result.latency_ms
    run.estimated_cost_usd += model_result.estimated_cost_usd
    run.final_response = model_result.text
    run.planned_tools = plan_tool_calls(run.task, state['agent'], state['connectors'])
    
    _log(state, 'plan_actions', 'planned_tool_calls', tool_count=len(run.planned_tools), provider=model_result.provider, model=model_result.model, model_error=model_result.error)
    save_run(_get_db_path(state), run)
    return state


def _policy_check(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    db_path = _get_db_path(state)
    risk_score, flags = assess_task_risk(run.task, state['policies'])
    run.risk_score = risk_score
    run.risk_flags.extend(flags)
    run.planned_tools = policy_check_tool_calls(run.planned_tools, risk_score)
    
    # If risk is critical and score is high, block execution
    if any(f.severity == 'critical' for f in flags) and risk_score >= 80:
        run.status = 'blocked'
    else:
        run.status = 'planned'
        
    _log(state, 'policy_check', 'evaluated_policy_rules', risk_score=risk_score, flags=len(flags), status=run.status)
    
    # Log incident reports for critical risks
    for flag in flags:
        if flag.severity in {'high', 'critical'}:
            inc = Incident(
                incident_id=new_id("inc"),
                severity=flag.severity,
                status="open",
                related_agent_id=run.agent_id,
                related_run_id=run.run_id,
                related_connector="",
                incident_type=flag.category,
                timeline=json.dumps([{"time": now_iso(), "event": f"Policy breach: {flag.message}"}]),
                assigned_owner="SecOps Reviewer",
                resolution_notes="",
                created_at=now_iso()
            )
            save_incident(db_path, inc)
            _log(state, 'policy_check', 'security_incident_alert_created', incident_id=inc.incident_id, type=inc.incident_type)
            
    save_run(db_path, run)
    return state


def _approval_gate(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    db_path = _get_db_path(state)
    if run.status == 'blocked':
        _log(state, 'approval_gate', 'blocked_before_approval', reason='critical_policy_risk')
        return state
        
    approvals: list[ApprovalRequest] = []
    for call in run.planned_tools:
        if call.requires_approval:
            # Create interactive approval request
            app_req = ApprovalRequest(
                approval_id=new_id("approval"),
                tool_call_id=call.call_id,
                tool_name=call.tool_name,
                reason=f"{call.tool_name} is marked {call.risk_level} risk or outside allowed tool permissions.",
                status='pending',
                agent_id=run.agent_id,
                requested_action=json.dumps(call.arguments),
                proposed_output="Simulation payload prepared.",
                reviewer="",
                decision_date="",
                decision_reason="",
                risk_level=call.risk_level
            )
            approvals.append(app_req)
            
    run.approvals = approvals
    run.status = 'awaiting_approval' if approvals else 'planned'
    _log(state, 'approval_gate', 'created_approval_requests', approval_count=len(approvals), status=run.status)
    save_run(db_path, run)
    return state


def _execute_tools(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    db_path = _get_db_path(state)
    approval_mode = state.get('approval_mode', 'manual_review')
    
    if run.status == 'blocked':
        _log(state, 'execute_tools', 'skipped_execution_blocked')
        return state
        
    # Auto-approve logic: approve if mode is auto-approve and risk score is low-medium
    auto_approve = (approval_mode == 'auto_approve_low_medium') and (run.risk_score < 75)
    executed = pending = blocked_calls = 0
    updated = []
    
    for call in run.planned_tools:
        approved = auto_approve or not call.requires_approval
        new_call = execute_tool_call(call, approved=approved)
        updated.append(new_call)
        
        if new_call.status in {'approved', 'not_required'}: 
            executed += 1
        elif new_call.status == 'pending': 
            pending += 1
        elif new_call.status == 'blocked':
            blocked_calls += 1
            
            # Log tool execution blocks in Incidents
            inc = Incident(
                incident_id=new_id("inc"),
                severity="critical",
                status="open",
                related_agent_id=run.agent_id,
                related_run_id=run.run_id,
                related_connector=call.tool_name,
                incident_type="tool_execution_blocked",
                timeline=json.dumps([{"time": now_iso(), "event": f"Tool execution blocked: {call.tool_name} query shield triggered."}]),
                assigned_owner="DBA Reviewer",
                resolution_notes="",
                created_at=now_iso()
            )
            save_incident(db_path, inc)
            _log(state, 'execute_tools', 'tool_execution_blocked_incident', tool_name=call.tool_name, incident_id=inc.incident_id)

    run.planned_tools = updated
    if blocked_calls > 0:
        run.status = 'blocked'
    elif pending > 0:
        run.status = 'awaiting_approval'
    else:
        run.status = 'executed'
        
    _log(state, 'execute_tools', 'processed_connector_calls', executed=executed, pending=pending, blocked=blocked_calls, auto_approve=auto_approve)
    save_run(db_path, run)
    return state


def _validate_result(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    db_path = _get_db_path(state)
    if run.status == 'blocked':
        run.final_response = 'Execution blocked by AgentOps Guard. The action triggered a high-severity security rule violation.'
    elif run.status == 'awaiting_approval':
        run.final_response += '\n\n🛡️ [AgentOps Guard] Action pending approval. One or more external tools are awaiting human authorization.'
    elif run.status == 'executed':
        run.final_response += '\n\n🛡️ [AgentOps Guard] Actions completed safely. Simulated connector payloads executed and logged.'
        run.status = 'completed'
        
    _log(state, 'validate_result', 'validated_final_response', final_status=run.status)
    save_run(db_path, run)
    return state


def _audit_log(state: AgentOpsState) -> AgentOpsState:
    _log(state, 'audit_log', 'finalized_audit_log', events=len(state['run'].audit_log), tool_calls=len(state['run'].planned_tools))
    save_run(_get_db_path(state), state['run'])
    return state


def build_agentops_graph():
    try:
        from langgraph.graph import END, StateGraph
    except Exception as exc:
        raise RuntimeError('LangGraph is not installed. Run: pip install langgraph langchain-core') from exc
        
    graph = StateGraph(AgentOpsState)
    for name, fn in [
        ('receive_task', _receive_task), ('classify_intent', _classify_intent), ('retrieve_context', _retrieve_context),
        ('plan_actions', _plan_actions), ('policy_check', _policy_check), ('approval_gate', _approval_gate),
        ('execute_tools', _execute_tools), ('validate_result', _validate_result), ('audit_log', _audit_log)]:
        graph.add_node(name, fn)
        
    graph.set_entry_point('receive_task')
    edges = ['receive_task','classify_intent','retrieve_context','plan_actions','policy_check','approval_gate','execute_tools','validate_result','audit_log']
    for a,b in zip(edges, edges[1:]):
        graph.add_edge(a,b)
    graph.add_edge('audit_log', END)
    return graph.compile()


def run_agentops_graph(
    task: str, 
    agent: AgentProfile, 
    connectors: list[ToolConnector], 
    policies: list[PolicyRule], 
    provider_router: ProviderRouter, 
    provider_choice: str = 'auto', 
    approval_mode: str = 'manual_review',
    db_path: Path | str = ""
) -> GraphRunResult:
    app = build_agentops_graph()
    state: AgentOpsState = {
        'task': task, 
        'agent': agent, 
        'connectors': connectors, 
        'policies': policies, 
        'provider_router': provider_router, 
        'provider_choice': provider_choice, 
        'approval_mode': approval_mode,
        'db_path': db_path
    }
    final_state = app.invoke(state)
    run = final_state['run']
    return GraphRunResult(run=run, trace=run.audit_log)

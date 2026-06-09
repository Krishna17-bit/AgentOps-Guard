
from __future__ import annotations
from typing import Any, TypedDict
from dataclasses import dataclass
from .models import AgentProfile, ToolConnector, PolicyRule, AgentRun, ApprovalRequest, now_iso
from .provider_router import ProviderRouter
from .policy import assess_task_risk, infer_intent, plan_tool_calls, policy_check_tool_calls
from .connectors import execute_tool_call


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


@dataclass
class GraphRunResult:
    run: AgentRun
    trace: list[dict[str, Any]]


def _log(state: AgentOpsState, node: str, action: str, **details: Any) -> None:
    event = {'time': now_iso(), 'node': node, 'action': action, **details}
    state['run'].audit_log.append(event)


def _receive_task(state: AgentOpsState) -> AgentOpsState:
    agent = state['agent']
    state['run'] = AgentRun(agent_id=agent.agent_id, agent_name=agent.name, task=state['task'], provider=state.get('provider_choice', 'auto'), status='planned')
    _log(state, 'receive_task', 'created_agent_run', agent=agent.name)
    return state


def _classify_intent(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    run.intent = infer_intent(run.task)
    _log(state, 'classify_intent', 'classified_task_intent', intent=run.intent)
    return state


def _retrieve_context(state: AgentOpsState) -> AgentOpsState:
    agent = state['agent']
    enabled = ', '.join([(c.real_connector or c.tool_name) for c in state['connectors'] if c.enabled])
    state['context'] = f"Agent: {agent.name}\nOwner: {agent.owner}\nAllowed tools: {', '.join(agent.allowed_tools)}\nEnabled connectors: {enabled}\nWorkspace: demo-safe connector registry with optional real connectors through .env."
    _log(state, 'retrieve_context', 'assembled_workspace_context', allowed_tool_count=len(agent.allowed_tools))
    return state


def _plan_actions(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    router = state['provider_router']
    prompt = f"""
Task:
{run.task}

Context:
{state.get('context', '')}

Return a concise governance-aware action plan. Mention connector calls, risks, and approvals.
"""
    model_result = router.generate(prompt, system='You are an AI agent governance control tower. Plan safe tool actions only. Never bypass approval.', provider=state.get('provider_choice', 'auto'))
    run.provider = model_result.provider
    run.model = model_result.model
    run.latency_ms += model_result.latency_ms
    run.estimated_cost_usd += model_result.estimated_cost_usd
    run.final_response = model_result.text
    run.planned_tools = plan_tool_calls(run.task, state['agent'], state['connectors'])
    _log(state, 'plan_actions', 'planned_tool_calls', tool_count=len(run.planned_tools), provider=model_result.provider, model=model_result.model, model_error=model_result.error)
    return state


def _policy_check(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    risk_score, flags = assess_task_risk(run.task, state['policies'])
    run.risk_score = risk_score
    run.risk_flags.extend(flags)
    run.planned_tools = policy_check_tool_calls(run.planned_tools, risk_score)
    run.status = 'blocked' if any(f.severity == 'critical' for f in flags) and risk_score >= 85 else 'planned'
    _log(state, 'policy_check', 'evaluated_policy_rules', risk_score=risk_score, flags=len(flags), status=run.status)
    return state


def _approval_gate(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    if run.status == 'blocked':
        _log(state, 'approval_gate', 'blocked_before_approval', reason='critical_policy_risk')
        return state
    approvals: list[ApprovalRequest] = []
    for call in run.planned_tools:
        if call.requires_approval:
            approvals.append(ApprovalRequest(tool_call_id=call.call_id, tool_name=call.tool_name, reason=f'{call.tool_name} is {call.risk_level} risk or requires configured approval.'))
    run.approvals = approvals
    run.status = 'awaiting_approval' if approvals else 'planned'
    _log(state, 'approval_gate', 'created_approval_requests', approval_count=len(approvals), status=run.status)
    return state


def _execute_tools(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    approval_mode = state.get('approval_mode', 'manual_review')
    if run.status == 'blocked':
        _log(state, 'execute_tools', 'skipped_execution_blocked')
        return state
    auto_approve = approval_mode == 'auto_approve_low_medium' and run.risk_score < 80
    executed = pending = 0
    updated = []
    for call in run.planned_tools:
        approved = auto_approve or not call.requires_approval
        new_call = execute_tool_call(call, approved=approved)
        updated.append(new_call)
        if new_call.status in {'approved', 'not_required'}: executed += 1
        elif new_call.status == 'pending': pending += 1
    run.planned_tools = updated
    run.status = 'awaiting_approval' if pending else 'executed'
    _log(state, 'execute_tools', 'processed_connector_calls', executed=executed, pending=pending, auto_approve=auto_approve)
    return state


def _validate_result(state: AgentOpsState) -> AgentOpsState:
    run = state['run']
    if run.status == 'blocked':
        run.final_response = 'Run blocked by AgentOps Guard because critical policy risk was detected. Human review is required.'
    elif run.status == 'awaiting_approval':
        run.final_response += '\n\nGovernance status: one or more connector actions are awaiting human approval.'
    elif run.status == 'executed':
        run.final_response += '\n\nGovernance status: approved/safe connector actions were simulated or executed and logged.'
        run.status = 'completed'
    _log(state, 'validate_result', 'validated_final_response', final_status=run.status)
    return state


def _audit_log(state: AgentOpsState) -> AgentOpsState:
    _log(state, 'audit_log', 'finalized_audit_log', events=len(state['run'].audit_log), tool_calls=len(state['run'].planned_tools))
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


def run_agentops_graph(task: str, agent: AgentProfile, connectors: list[ToolConnector], policies: list[PolicyRule], provider_router: ProviderRouter, provider_choice: str = 'auto', approval_mode: str = 'manual_review') -> GraphRunResult:
    app = build_agentops_graph()
    state: AgentOpsState = {'task': task, 'agent': agent, 'connectors': connectors, 'policies': policies, 'provider_router': provider_router, 'provider_choice': provider_choice, 'approval_mode': approval_mode}
    final_state = app.invoke(state)
    run = final_state['run']
    return GraphRunResult(run=run, trace=run.audit_log)

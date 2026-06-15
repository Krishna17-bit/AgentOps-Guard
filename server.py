from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Optional
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from src.database import (
    init_db, get_agents, save_agent, delete_agent,
    get_connectors, save_connector, delete_connector,
    get_policies, save_policy, delete_policy,
    get_runs, get_run, update_approval_status,
    get_incidents, update_incident_status, get_platform_audit_logs, log_platform_action, save_run
)
from src.models import AgentProfile, ToolConnector, PolicyRule, AgentRun, Incident, ToolCall, ApprovalRequest, RiskFlag
from src.agent_graph import run_agentops_graph
from src.provider_router import ProviderRouter
from src.policy import scan_prompt_for_injection, assess_task_risk
from src.evaluation import evaluate_run
from src.data import load_eval_cases

# Config & Directories
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / 'outputs'
DB_PATH = OUTPUT_DIR / 'agentops_guard.db'

# Init FastAPI
app = FastAPI(
    title="AgentOps Guard API",
    description="Governance, Connector Control, Observability and Risk Scanner layer for AI Agents.",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB initialization on startup
@app.on_event("startup")
def startup_db():
    init_db(DB_PATH, BASE_DIR)


# --- Models for Request Bodies ---
class RunRequest(BaseModel):
    agent_id: str
    task: str
    provider: Optional[str] = "auto"
    approval_mode: Optional[str] = "manual_review"

class ScanRequest(BaseModel):
    prompt: str

class DecisionRequest(BaseModel):
    reviewer: str
    reason: str

class IncidentUpdateRequest(BaseModel):
    status: str
    assigned_owner: Optional[str] = ""
    resolution_notes: Optional[str] = ""
    actor: Optional[str] = "API_User"


# --- API Endpoints ---

@app.get("/health")
def health_check():
    router = ProviderRouter()
    return {
        "status": "healthy",
        "database": "online",
        "provider_status": router.status
    }


# 1. Agents API
@app.get("/api/agents")
def read_agents():
    return get_agents(DB_PATH)

@app.post("/api/agents")
def create_new_agent(agent: AgentProfile):
    save_agent(DB_PATH, agent, actor="API_User")
    return {"message": f"Agent {agent.name} saved successfully.", "agent_id": agent.agent_id}

@app.get("/api/agents/{agent_id}")
def read_agent(agent_id: str):
    agents = get_agents(DB_PATH)
    for a in agents:
        if a.agent_id == agent_id:
            return a
    raise HTTPException(status_code=404, detail="Agent profile not found.")

@app.patch("/api/agents/{agent_id}")
def patch_agent(agent_id: str, updates: dict = Body(...)):
    agents = get_agents(DB_PATH)
    target = None
    for a in agents:
        if a.agent_id == agent_id:
            target = a
            break
    if not target:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    
    # Apply updates
    data = target.model_dump()
    data.update(updates)
    updated_agent = AgentProfile(**data)
    save_agent(DB_PATH, updated_agent, actor="API_User")
    return {"message": "Agent profile updated successfully.", "agent": updated_agent}

@app.post("/api/agents/{agent_id}/disable")
def disable_agent_endpoint(agent_id: str):
    agents = get_agents(DB_PATH)
    target = None
    for a in agents:
        if a.agent_id == agent_id:
            target = a
            break
    if not target:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    target.status = "disabled"
    save_agent(DB_PATH, target, actor="API_User")
    return {"message": f"Agent {target.name} has been disabled."}


# 2. Connectors API
@app.get("/api/connectors")
def read_connectors():
    return get_connectors(DB_PATH)

@app.post("/api/connectors")
def create_new_connector(conn: ToolConnector):
    save_connector(DB_PATH, conn, actor="API_User")
    return {"message": f"Connector {conn.tool_name} saved successfully."}

@app.patch("/api/connectors/{tool_name}")
def patch_connector(tool_name: str, updates: dict = Body(...)):
    conns = get_connectors(DB_PATH)
    target = None
    for c in conns:
        if c.tool_name == tool_name:
            target = c
            break
    if not target:
        raise HTTPException(status_code=404, detail="Connector target not found.")
    
    data = target.model_dump()
    data.update(updates)
    updated_conn = ToolConnector(**data)
    save_connector(DB_PATH, updated_conn, actor="API_User")
    return {"message": f"Connector {tool_name} updated successfully."}

@app.post("/api/connectors/{tool_name}/test")
def test_connector_endpoint(tool_name: str):
    conns = get_connectors(DB_PATH)
    target = None
    for c in conns:
        if c.tool_name == tool_name:
            target = c
            break
    if not target:
        raise HTTPException(status_code=404, detail="Connector target not found.")
        
    # Run a credentials diagnostic test
    needed_vars = [x.strip() for x in target.env_vars.split(';') if x.strip()]
    missing = [v for v in needed_vars if not os.getenv(v, '').strip()]
    
    if missing:
        return {"status": "unconfigured", "missing_variables": missing, "details": "Real connection will fall back to simulation."}
    return {"status": "ready", "details": "All required environment credentials found. Connector ready."}


# 3. Policies API
@app.get("/api/policies")
def read_policies():
    return get_policies(DB_PATH)

@app.post("/api/policies")
def create_new_policy(policy: PolicyRule):
    save_policy(DB_PATH, policy, actor="API_User")
    return {"message": f"Policy {policy.name} saved successfully."}

@app.patch("/api/policies/{policy_id}")
def patch_policy(policy_id: str, updates: dict = Body(...)):
    pols = get_policies(DB_PATH)
    target = None
    for p in pols:
        if p.policy_id == policy_id:
            target = p
            break
    if not target:
        raise HTTPException(status_code=404, detail="Policy rule not found.")
        
    data = target.model_dump()
    data.update(updates)
    updated_pol = PolicyRule(**data)
    save_policy(DB_PATH, updated_pol, actor="API_User")
    return {"message": f"Policy rule {policy_id} updated successfully."}


# 4. Risk / Prompt Injection Scanner API
@app.post("/api/prompt-injection/scan")
def scan_prompt_endpoint(req: ScanRequest):
    res = scan_prompt_for_injection(req.prompt)
    return res

@app.post("/api/risk/scan")
def scan_risk_endpoint(req: ScanRequest):
    policies = get_policies(DB_PATH)
    score, flags = assess_task_risk(req.prompt, policies)
    return {
        "risk_score": score,
        "flags_triggered": [f.model_dump() for f in flags],
        "safe": score < 80
    }


# 5. Approvals API
@app.get("/api/approvals")
def read_approvals():
    runs = get_runs(DB_PATH)
    pending = []
    for r in runs:
        for a in r.approvals:
            if a.status == "pending":
                pending.append(a)
    return pending

@app.post("/api/approvals/{approval_id}/approve")
def approve_request(approval_id: str, req: DecisionRequest):
    ok = update_approval_status(DB_PATH, approval_id, "approved", req.reviewer, req.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return {"message": f"Request {approval_id} approved."}

@app.post("/api/approvals/{approval_id}/reject")
def reject_request(approval_id: str, req: DecisionRequest):
    ok = update_approval_status(DB_PATH, approval_id, "rejected", req.reviewer, req.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return {"message": f"Request {approval_id} rejected."}


# 6. Runs API (sandbox execution engine)
@app.get("/api/runs")
def read_runs():
    return get_runs(DB_PATH)

@app.get("/api/runs/{run_id}")
def read_run_by_id(run_id: str):
    r = get_run(DB_PATH, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run log not found.")
    return r

@app.post("/api/runs")
def run_governed_task(req: RunRequest):
    agents = get_agents(DB_PATH)
    agent = None
    for a in agents:
        if a.agent_id == req.agent_id:
            agent = a
            break
            
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not registered in database.")
    if agent.status != "active":
        raise HTTPException(status_code=400, detail=f"Agent profile '{agent.name}' is currently inactive ({agent.status}).")
        
    connectors = get_connectors(DB_PATH)
    policies = get_policies(DB_PATH)
    router = ProviderRouter()
    
    # Run the graph pipeline
    res = run_agentops_graph(
        task=req.task,
        agent=agent,
        connectors=connectors,
        policies=policies,
        provider_router=router,
        provider_choice=req.provider,
        approval_mode=req.approval_mode,
        db_path=DB_PATH
    )
    
    return {
        "run_id": res.run.run_id,
        "status": res.run.status,
        "risk_score": res.run.risk_score,
        "intent": res.run.intent,
        "final_response": res.run.final_response,
        "planned_tools": res.run.planned_tools,
        "approvals_created": len(res.run.approvals),
        "audit_trail_events": len(res.run.audit_log)
    }


# 7. Evals API
@app.get("/api/evals")
def read_eval_cases():
    return load_eval_cases(BASE_DIR)

@app.post("/api/evals/run")
def run_evals_suite():
    eval_cases = load_eval_cases(BASE_DIR)
    agents = get_agents(DB_PATH)
    connectors = get_connectors(DB_PATH)
    policies = get_policies(DB_PATH)
    router = ProviderRouter()
    
    if not agents:
         raise HTTPException(status_code=400, detail="Cannot run evals: agent registry database is empty.")
         
    agent_map = {a.agent_id: a for a in agents}
    results = []
    
    for case in eval_cases:
        agent = agent_map.get(case.agent_id, agents[0])
        res = run_agentops_graph(
            task=case.task,
            agent=agent,
            connectors=connectors,
            policies=policies,
            provider_router=router,
            provider_choice='mock',
            approval_mode='manual_review',
            db_path=DB_PATH
        )
        score_res = evaluate_run(res.run, case)
        results.append(score_res)
        
    return {
        "pass_rate_pct": int((sum(1 for r in results if r.passed) / len(results)) * 100),
        "average_score": int(sum(r.score for r in results) / len(results)),
        "results": results
    }


# 8. Incidents API
@app.get("/api/incidents")
def read_incidents():
    return get_incidents(DB_PATH)

@app.patch("/api/incidents/{incident_id}")
def triage_incident(incident_id: str, req: IncidentUpdateRequest):
    ok = update_incident_status(DB_PATH, incident_id, req.status, req.assigned_owner, req.resolution_notes, actor=req.actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Incident report not found.")
    return {"message": f"Incident {incident_id} successfully updated."}


# 9. Audit Logs API
@app.get("/api/audit-logs")
def read_platform_audit_logs():
    return get_platform_audit_logs(DB_PATH)

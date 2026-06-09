
from __future__ import annotations
import os
import json
import requests
from dotenv import load_dotenv
from .models import ToolCall

load_dotenv()


def real_connectors_enabled() -> bool:
    return os.getenv('ENABLE_REAL_CONNECTORS', 'false').strip().lower() in {'true', '1', 'yes'}


def connector_readiness() -> dict[str, bool]:
    return {
        'slack.notify': bool(os.getenv('SLACK_WEBHOOK_URL', '').strip()),
        'github.create_issue': bool(os.getenv('GITHUB_TOKEN', '').strip() and os.getenv('GITHUB_REPO', '').strip()),
        'gmail.send_email': bool(os.getenv('GMAIL_SMTP_HOST', '').strip() and os.getenv('GMAIL_SMTP_USER', '').strip() and os.getenv('GMAIL_SMTP_PASSWORD', '').strip()),
        'database.query': bool(os.getenv('DATABASE_URL', '').strip()),
        'hubspot.create_contact': bool(os.getenv('HUBSPOT_API_KEY', '').strip()),
        'notion.create_page': bool(os.getenv('NOTION_API_KEY', '').strip()),
    }


def execute_tool_call(call: ToolCall, approved: bool = False) -> ToolCall:
    """
    Safe connector layer.
    - Public demo: simulation only.
    - Client deployment: set ENABLE_REAL_CONNECTORS=true and configure env keys.
    - Approval gate still applies before real execution.
    """
    if call.status == 'blocked':
        return call
    if call.requires_approval and not approved:
        call.status = 'pending'
        call.result = 'Awaiting human approval. Connector was not executed.'
        return call

    if not real_connectors_enabled():
        call.status = 'approved' if call.requires_approval else 'not_required'
        call.result = f'SIMULATED: {call.tool_name} payload prepared. Set ENABLE_REAL_CONNECTORS=true in a trusted workspace for real execution.'
        return call

    try:
        if call.tool_name == 'slack.notify':
            return _slack_notify(call)
        if call.tool_name == 'github.create_issue':
            return _github_create_issue(call)
        if call.tool_name in {'database.query', 'snowflake.query'}:
            q = str(call.arguments.get('query', ''))
            if any(x in q.lower() for x in ['drop ', 'delete ', 'truncate ', 'update ', 'insert ', 'alter ']):
                call.status = 'blocked'
                call.result = 'Blocked: only read-only queries are allowed by the connector guard.'
                return call
            call.status = 'approved' if call.requires_approval else 'not_required'
            call.result = 'REAL CONNECTOR PLACEHOLDER: read-only query guard passed. Add DB execution in client workspace.'
            return call
        call.status = 'approved' if call.requires_approval else 'not_required'
        call.result = f'REAL CONNECTOR PLACEHOLDER: {call.tool_name} is configured for future client implementation.'
        return call
    except Exception as exc:
        call.status = 'blocked'
        call.result = f'Connector error: {exc}'
        return call


def _slack_notify(call: ToolCall) -> ToolCall:
    url = os.getenv('SLACK_WEBHOOK_URL', '').strip()
    if not url:
        call.result = 'Slack webhook missing. Add SLACK_WEBHOOK_URL.'
        call.status = 'pending'
        return call
    payload = {'text': call.arguments.get('message', 'AgentOps Guard notification')}
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    call.status = 'approved' if call.requires_approval else 'not_required'
    call.result = 'Slack notification sent.'
    return call


def _github_create_issue(call: ToolCall) -> ToolCall:
    token = os.getenv('GITHUB_TOKEN', '').strip()
    repo = os.getenv('GITHUB_REPO', '').strip()
    if not token or not repo:
        call.result = 'GitHub token/repo missing. Add GITHUB_TOKEN and GITHUB_REPO.'
        call.status = 'pending'
        return call
    url = f'https://api.github.com/repos/{repo}/issues'
    payload = {'title': call.arguments.get('title', 'AgentOps Guard Issue'), 'body': call.arguments.get('description', '')}
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    call.status = 'approved' if call.requires_approval else 'not_required'
    call.result = 'GitHub issue created.'
    return call

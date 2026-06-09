
from __future__ import annotations
from pathlib import Path
import json
import sqlite3
import zipfile
import pandas as pd
from .models import AgentRun, now_iso


def runs_to_df(runs: list[AgentRun]) -> pd.DataFrame:
    return pd.DataFrame([{
        'run_id': r.run_id, 'created_at': r.created_at, 'agent': r.agent_name, 'task': r.task,
        'provider': r.provider, 'model': r.model, 'status': r.status, 'intent': r.intent,
        'risk_score': r.risk_score, 'risk_flags': len(r.risk_flags), 'tool_calls': len(r.planned_tools),
        'approvals': len(r.approvals), 'latency_ms': r.latency_ms, 'estimated_cost_usd': r.estimated_cost_usd,
    } for r in runs])


def tool_calls_df(runs: list[AgentRun]) -> pd.DataFrame:
    rows = []
    for r in runs:
        for c in r.planned_tools:
            rows.append({'run_id': r.run_id, 'agent': r.agent_name, 'tool_call_id': c.call_id, 'tool_name': c.tool_name, 'risk_level': c.risk_level, 'requires_approval': c.requires_approval, 'status': c.status, 'result': c.result, 'arguments': json.dumps(c.arguments, default=str)})
    return pd.DataFrame(rows)


def risk_flags_df(runs: list[AgentRun]) -> pd.DataFrame:
    rows = []
    for r in runs:
        for f in r.risk_flags:
            rows.append({'run_id': r.run_id, 'agent': r.agent_name, 'severity': f.severity, 'category': f.category, 'message': f.message, 'evidence': f.evidence})
    return pd.DataFrame(rows)


def approvals_df(runs: list[AgentRun]) -> pd.DataFrame:
    rows = []
    for r in runs:
        for a in r.approvals:
            rows.append({'run_id': r.run_id, 'approval_id': a.approval_id, 'tool_call_id': a.tool_call_id, 'tool_name': a.tool_name, 'reason': a.reason, 'status': a.status, 'created_at': a.created_at})
    return pd.DataFrame(rows)


def audit_df(runs: list[AgentRun]) -> pd.DataFrame:
    rows = []
    for r in runs:
        for e in r.audit_log:
            row = {'run_id': r.run_id, 'agent': r.agent_name}; row.update(e); rows.append(row)
    return pd.DataFrame(rows)


def save_runs_sqlite(runs: list[AgentRun], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        runs_to_df(runs).to_sql('runs', conn, if_exists='replace', index=False)
        tool_calls_df(runs).to_sql('tool_calls', conn, if_exists='replace', index=False)
        risk_flags_df(runs).to_sql('risk_flags', conn, if_exists='replace', index=False)
        approvals_df(runs).to_sql('approvals', conn, if_exists='replace', index=False)
        audit_df(runs).to_sql('audit_log', conn, if_exists='replace', index=False)


def governance_report(runs: list[AgentRun]) -> str:
    total = len(runs); blocked = len([r for r in runs if r.status == 'blocked']); waiting = len([r for r in runs if r.status == 'awaiting_approval']); completed = len([r for r in runs if r.status == 'completed']); high_risk = len([r for r in runs if r.risk_score >= 55])
    lines = ['# AgentOps Guard Governance Report', '', f'Generated: {now_iso()}', '', '## Summary', f'- Total runs: {total}', f'- Completed runs: {completed}', f'- Awaiting approval: {waiting}', f'- Blocked runs: {blocked}', f'- High/critical-risk runs: {high_risk}', '', '## Recent Runs']
    for r in runs[-20:]:
        lines += [f'### {r.agent_name} · {r.run_id}', f'- Status: {r.status}', f'- Risk score: {r.risk_score}', f'- Intent: {r.intent}', f'- Provider/model: {r.provider} / {r.model}', f'- Tool calls: {len(r.planned_tools)}', f'- Approvals: {len(r.approvals)}', f'- Task: {r.task}', '']
    return '\n'.join(lines)


def make_audit_zip(runs: list[AgentRun], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {'generated_at': now_iso(), 'run_count': len(runs), 'runs': [r.model_dump() for r in runs]}
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('agent_runs.csv', runs_to_df(runs).to_csv(index=False))
        z.writestr('tool_calls.csv', tool_calls_df(runs).to_csv(index=False))
        z.writestr('risk_flags.csv', risk_flags_df(runs).to_csv(index=False))
        z.writestr('approvals.csv', approvals_df(runs).to_csv(index=False))
        z.writestr('audit_log.csv', audit_df(runs).to_csv(index=False))
        z.writestr('agentops_runs.json', json.dumps(payload, indent=2, default=str))
        z.writestr('governance_report.md', governance_report(runs))
    return output_path

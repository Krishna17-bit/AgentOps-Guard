from __future__ import annotations
from pathlib import Path
import json
import zipfile
import pandas as pd
from .models import AgentRun, now_iso
from .database import get_runs


def runs_to_df(runs: list[AgentRun]) -> pd.DataFrame:
    if not runs:
        return pd.DataFrame(columns=[
            'run_id', 'created_at', 'agent', 'task', 'provider', 'model', 
            'status', 'intent', 'risk_score', 'risk_flags', 'tool_calls', 
            'approvals', 'latency_ms', 'estimated_cost_usd'
        ])
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
            rows.append({
                'run_id': r.run_id, 
                'agent': r.agent_name, 
                'tool_call_id': c.call_id, 
                'tool_name': c.tool_name, 
                'risk_level': c.risk_level, 
                'requires_approval': c.requires_approval, 
                'status': c.status, 
                'result': c.result, 
                'arguments': json.dumps(c.arguments, default=str)
            })
    if not rows:
        return pd.DataFrame(columns=['run_id', 'agent', 'tool_call_id', 'tool_name', 'risk_level', 'requires_approval', 'status', 'result', 'arguments'])
    return pd.DataFrame(rows)


def risk_flags_df(runs: list[AgentRun]) -> pd.DataFrame:
    rows = []
    for r in runs:
        for f in r.risk_flags:
            rows.append({
                'run_id': r.run_id, 
                'agent': r.agent_name, 
                'severity': f.severity, 
                'category': f.category, 
                'message': f.message, 
                'evidence': f.evidence
            })
    if not rows:
        return pd.DataFrame(columns=['run_id', 'agent', 'severity', 'category', 'message', 'evidence'])
    return pd.DataFrame(rows)


def approvals_df(runs: list[AgentRun]) -> pd.DataFrame:
    rows = []
    for r in runs:
        for a in r.approvals:
            rows.append({
                'run_id': r.run_id, 
                'approval_id': a.approval_id, 
                'tool_call_id': a.tool_call_id, 
                'tool_name': a.tool_name, 
                'reason': a.reason, 
                'status': a.status, 
                'created_at': a.created_at,
                'reviewer': a.reviewer,
                'decision_date': a.decision_date,
                'decision_reason': a.decision_reason
            })
    if not rows:
        return pd.DataFrame(columns=['run_id', 'approval_id', 'tool_call_id', 'tool_name', 'reason', 'status', 'created_at', 'reviewer', 'decision_date', 'decision_reason'])
    return pd.DataFrame(rows)


def audit_df(runs: list[AgentRun]) -> pd.DataFrame:
    rows = []
    for r in runs:
        for e in r.audit_log:
            row = {'run_id': r.run_id, 'agent': r.agent_name}
            row.update(e)
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=['run_id', 'agent', 'time', 'node', 'action'])
    return pd.DataFrame(rows)


def governance_report(runs: list[AgentRun]) -> str:
    total = len(runs)
    blocked = len([r for r in runs if r.status == 'blocked'])
    waiting = len([r for r in runs if r.status == 'awaiting_approval'])
    completed = len([r for r in runs if r.status == 'completed'])
    high_risk = len([r for r in runs if r.risk_score >= 55])
    
    lines = [
        '# AgentOps Guard Governance Report', 
        '', 
        f'Generated: {now_iso()}', 
        '', 
        '## Summary Metrics', 
        f'- **Total Runs Governed**: {total}', 
        f'- **Completed Execution**: {completed}', 
        f'- **Awaiting Human Review**: {waiting}', 
        f'- **Blocked by Policy**: {blocked}', 
        f'- **High/Critical Risk Runs**: {high_risk}', 
        '', 
        '## Audit Trail Summary'
    ]
    
    for r in runs[-15:]:
        lines += [
            f'### Run ID: {r.run_id} ({r.agent_name})', 
            f'- **Task Input**: `{r.task}`',
            f'- **Status**: `{r.status}`', 
            f'- **Risk Score**: `{r.risk_score}`', 
            f'- **Provider / Model**: `{r.provider}` / `{r.model}`', 
            f'- **Actions Evaluated**: {len(r.planned_tools)} calls', 
            f'- **Approvals Required**: {len(r.approvals)} items', 
            f'- **Final Response Output**: *{r.final_response}*',
            ''
        ]
    return '\n'.join(lines)


def make_audit_zip(db_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runs = get_runs(db_path)
    
    payload = {
        'generated_at': now_iso(), 
        'run_count': len(runs), 
        'runs': [r.model_dump() for r in runs]
    }
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('agent_runs.csv', runs_to_df(runs).to_csv(index=False))
        z.writestr('tool_calls.csv', tool_calls_df(runs).to_csv(index=False))
        z.writestr('risk_flags.csv', risk_flags_df(runs).to_csv(index=False))
        z.writestr('approvals.csv', approvals_df(runs).to_csv(index=False))
        z.writestr('audit_log.csv', audit_df(runs).to_csv(index=False))
        z.writestr('agentops_runs.json', json.dumps(payload, indent=2, default=str))
        z.writestr('governance_report.md', governance_report(runs))
        
    return output_path

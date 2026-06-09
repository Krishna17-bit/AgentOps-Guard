from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .models import AgentProfile, ToolConnector, PolicyRule, EvalCase


def _is_missing(value: Any) -> bool:
    """
    Handles None, empty strings, and pandas NaN values safely.
    """
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except Exception:
        pass

    if isinstance(value, str) and not value.strip():
        return True

    return False


def _safe_str(value: Any, default: str = "") -> str:
    """
    Convert CSV/Excel empty cells, NaN, None into safe strings.
    This prevents Pydantic errors like:
    env_vars Input should be a valid string, input_value=nan
    """
    if _is_missing(value):
        return default

    return str(value).strip()


def _split_tools(value: Any) -> list[str]:
    if _is_missing(value):
        return []

    text = str(value).strip()

    if not text:
        return []

    return [
        x.strip()
        for x in text.replace(",", ";").split(";")
        if x.strip()
    ]


def _bool(value: Any, default: bool = True) -> bool:
    if _is_missing(value):
        return default

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
        "enabled",
        "active",
    }


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Convert all pandas NaN values to safe defaults before passing into Pydantic.
    """
    clean = {}

    for key, value in record.items():
        if _is_missing(value):
            clean[key] = ""
        else:
            clean[key] = value

    return clean


def load_agents(base_dir: Path) -> list[AgentProfile]:
    df = pd.read_csv(base_dir / "sample_data" / "agents.csv")
    df = df.where(pd.notna(df), "")

    agents: list[AgentProfile] = []

    for r in df.to_dict(orient="records"):
        r = _clean_record(r)

        r["agent_id"] = _safe_str(r.get("agent_id"))
        r["name"] = _safe_str(r.get("name"))
        r["description"] = _safe_str(r.get("description"))
        r["risk_level"] = _safe_str(r.get("risk_level"), "medium") or "medium"
        r["allowed_tools"] = _split_tools(r.get("allowed_tools", ""))
        r["owner"] = _safe_str(r.get("owner"), "Ops") or "Ops"

        try:
            r["budget_limit_usd"] = float(r.get("budget_limit_usd") or 5.0)
        except Exception:
            r["budget_limit_usd"] = 5.0

        agents.append(AgentProfile(**r))

    return agents


def load_connectors(base_dir: Path) -> list[ToolConnector]:
    df = pd.read_csv(base_dir / "sample_data" / "connectors.csv")
    df = df.where(pd.notna(df), "")

    connectors: list[ToolConnector] = []

    for r in df.to_dict(orient="records"):
        r = _clean_record(r)

        # Required/basic fields
        r["tool_name"] = _safe_str(r.get("tool_name"))
        r["category"] = _safe_str(r.get("category"), "general") or "general"
        r["description"] = _safe_str(r.get("description"))
        r["risk_level"] = _safe_str(r.get("risk_level"), "medium") or "medium"

        # New v2 connector fields
        r["real_connector"] = _safe_str(
            r.get("real_connector"),
            r.get("tool_name", ""),
        )

        r["env_vars"] = _safe_str(r.get("env_vars"), "")

        r["auth_type"] = _safe_str(
            r.get("auth_type"),
            "api_key",
        ) or "api_key"

        r["setup_notes"] = _safe_str(r.get("setup_notes"), "")

        # Booleans
        r["requires_approval"] = _bool(
            r.get("requires_approval"),
            True,
        )

        r["enabled"] = _bool(
            r.get("enabled"),
            True,
        )

        # Skip broken/empty rows
        if not r["tool_name"]:
            continue

        connectors.append(ToolConnector(**r))

    return connectors


def load_policies(base_dir: Path) -> list[PolicyRule]:
    df = pd.read_csv(base_dir / "sample_data" / "policies.csv")
    df = df.where(pd.notna(df), "")

    policies: list[PolicyRule] = []

    for r in df.to_dict(orient="records"):
        r = _clean_record(r)

        r["policy_id"] = _safe_str(r.get("policy_id"))
        r["name"] = _safe_str(r.get("name"))
        r["condition"] = _safe_str(r.get("condition"))
        r["severity"] = _safe_str(r.get("severity"), "medium") or "medium"
        r["action"] = _safe_str(r.get("action"), "require_approval") or "require_approval"

        if not r["policy_id"]:
            continue

        policies.append(PolicyRule(**r))

    return policies


def load_eval_cases(base_dir: Path) -> list[EvalCase]:
    df = pd.read_csv(base_dir / "sample_data" / "eval_cases.csv")
    df = df.where(pd.notna(df), "")

    cases: list[EvalCase] = []

    for r in df.to_dict(orient="records"):
        r = _clean_record(r)

        r["case_id"] = _safe_str(r.get("case_id"))
        r["agent_id"] = _safe_str(r.get("agent_id"))
        r["task"] = _safe_str(r.get("task"))
        r["expected_behavior"] = _safe_str(r.get("expected_behavior"))
        r["risk_expected"] = _safe_str(r.get("risk_expected"), "medium") or "medium"

        if not r["case_id"]:
            continue

        cases.append(EvalCase(**r))

    return cases


def read_uploaded_table(upload) -> pd.DataFrame | None:
    if upload is None:
        return None

    name = upload.name.lower()

    if name.endswith(".csv"):
        df = pd.read_csv(upload)
        return df.where(pd.notna(df), "")

    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(upload)
        return df.where(pd.notna(df), "")

    if name.endswith(".json"):
        obj = json.load(upload)

        if isinstance(obj, list):
            df = pd.DataFrame(obj)
            return df.where(pd.notna(df), "")

        if isinstance(obj, dict):
            for key in [
                "records",
                "data",
                "items",
                "rows",
                "tools",
                "agents",
                "connectors",
                "policies",
            ]:
                if isinstance(obj.get(key), list):
                    df = pd.DataFrame(obj[key])
                    return df.where(pd.notna(df), "")

            df = pd.DataFrame([obj])
            return df.where(pd.notna(df), "")

    return None


def connector_status(connectors: list[ToolConnector]) -> pd.DataFrame:
    rows = []

    for c in connectors:
        env_vars = _safe_str(getattr(c, "env_vars", ""), "")

        needed = [
            x.strip()
            for x in env_vars.split(";")
            if x.strip()
        ]

        configured = [
            x
            for x in needed
            if os.getenv(x, "").strip()
        ]

        ready = (not needed) or len(configured) == len(needed)

        rows.append(
            {
                "tool_name": c.tool_name,
                "real_connector": getattr(c, "real_connector", "") or c.tool_name,
                "category": c.category,
                "risk_level": c.risk_level,
                "requires_approval": c.requires_approval,
                "enabled": c.enabled,
                "env_vars_needed": "; ".join(needed),
                "configured_vars": "; ".join(configured),
                "connection_ready": ready,
            }
        )

    return pd.DataFrame(rows)
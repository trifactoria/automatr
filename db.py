#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional, cast

DEFAULT_DB_PATH = os.getenv("AUTOMATR_DB_PATH", "./data/automatr.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# ---------------------------
# Core DB helpers
# ---------------------------


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    Path(DEFAULT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.executescript(schema)
        conn.commit()


# ---------------------------
# Sanitization + validation
# ---------------------------

_VAR_RX_BAD = re.compile(r"[^a-z0-9_]+")
_VAR_RX_WS = re.compile(r"\s+")


def sanitize_var_name(name: str) -> str:
    """
    Your rule:
      - lowercase
      - spaces -> underscores
      - strip non [a-z0-9_]
      - collapse underscores
      - cannot start with digit (prefix '_')
      - must not become empty (fallback 'var')
    NOTE: This is used for collision detection and var reference validation.
    The UI should enforce uniqueness; export should fail if collisions occur anyway.
    """
    s = (name or "").strip().lower()
    s = _VAR_RX_WS.sub("_", s)
    s = _VAR_RX_BAD.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "var"
    if s[0].isdigit():
        s = "_" + s
    return s


def _dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ============================================================
# Containers
# ============================================================


def list_containers() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT name FROM containers ORDER BY name").fetchall()
    return [_dict(r) for r in rows]


def create_container(name: str, description: str = "") -> None:
    # schema.sql currently has only name, created_at. ignore description.
    with _connect() as conn:
        conn.execute("INSERT INTO containers(name) VALUES(?)", (name,))
        conn.commit()


def container_exists(name: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM containers WHERE name=?", (name,)).fetchone()
    return row is not None


# ============================================================
# Automations
# ============================================================


def list_automations() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name, description, updated_at, compiled_at FROM automations ORDER BY name"
        ).fetchall()
    return [_dict(r) for r in rows]


def upsert_automation(name: str, description: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO automations(name, description)
            VALUES(?, ?)
            ON CONFLICT(name) DO UPDATE SET
              description=excluded.description
            """,
            (name, description or ""),
        )
        conn.commit()


def get_automation(name: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT name, description, created_at, updated_at, compiled_at, compiled_hash
            FROM automations
            WHERE name=?
            """,
            (name,),
        ).fetchone()
    return _dict(row) if row else None


def delete_automation(name: str) -> bool:
    """
    Deletes an automation and its graph. Returns True if something was deleted.
    We delete children explicitly to avoid relying on ON DELETE CASCADE details.
    """
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Find step ids first
            step_rows = conn.execute(
                "SELECT id FROM automation_steps WHERE automation_name=?",
                (name,),
            ).fetchall()
            step_ids = [int(r["id"]) for r in step_rows]

            if step_ids:
                # Delete step children
                conn.executemany("DELETE FROM step_params WHERE step_id=?", [(sid,) for sid in step_ids])
                conn.executemany("DELETE FROM step_clauses WHERE step_id=?", [(sid,) for sid in step_ids])

            # Delete steps + vars
            conn.execute("DELETE FROM automation_steps WHERE automation_name=?", (name,))
            conn.execute("DELETE FROM automation_vars WHERE automation_name=?", (name,))

            # Delete automation row
            cur = conn.execute("DELETE FROM automations WHERE name=?", (name,))
            deleted = (cur.rowcount or 0) > 0

            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise


def set_compiled_script(name: str, compiled_py: str) -> None:
    compiled_py = compiled_py or ""
    h = _sha256(compiled_py) if compiled_py else None
    with _connect() as conn:
        conn.execute(
            """
            UPDATE automations
               SET compiled_py=?,
                   compiled_hash=?,
                   compiled_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
             WHERE name=?
            """,
            (compiled_py, h, name),
        )
        conn.commit()


def get_compiled_script(name: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT compiled_py FROM automations WHERE name=?",
            (name,),
        ).fetchone()
    return str(row["compiled_py"]) if row and row["compiled_py"] is not None else None


def list_distinct_step_actions() -> list[str]:
    """
    Used by /actions/check to see what actions are referenced in the DB.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT action FROM automation_steps ORDER BY action"
        ).fetchall()
    out: list[str] = []
    for r in rows:
        v = r["action"]
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out.append(s)
    return out


# ============================================================
# Vars
# ============================================================


def list_vars(automation_name: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT key, type, value, description
            FROM automation_vars
            WHERE automation_name=?
            ORDER BY key
            """,
            (automation_name,),
        ).fetchall()
    return [_dict(r) for r in rows]


# ============================================================
# Steps / params / clauses read helpers
# ============================================================


def list_steps(automation_name: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, step_num, label, action, enabled, note
            FROM automation_steps
            WHERE automation_name=?
            ORDER BY step_num
            """,
            (automation_name,),
        ).fetchall()
    return [_dict(r) for r in rows]


def list_step_params(step_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT key, type, value
            FROM step_params
            WHERE step_id=?
            ORDER BY key
            """,
            (int(step_id),),
        ).fetchall()
    return [_dict(r) for r in rows]


def list_step_clauses(step_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
              id, clause_order, head,
              lhs_kind, lhs_type, lhs_value,
              op,
              rhs_kind, rhs_type, rhs_value,
              action, stop_tag, action_value,
              note
            FROM step_clauses
            WHERE step_id=?
            ORDER BY clause_order
            """,
            (int(step_id),),
        ).fetchall()
    return [_dict(r) for r in rows]


def get_automation_full(name: str) -> Optional[dict[str, Any]]:
    """
    Legacy shape (kept for compatibility):
      {"automation": {...}, "vars": [...], "steps": [...]}
    """
    auto = get_automation(name)
    if not auto:
        return None

    vars_ = list_vars(name)
    steps = list_steps(name)
    for s in steps:
        sid = int(s["id"])
        s["params"] = list_step_params(sid)
        s["clauses"] = list_step_clauses(sid)

    return {"automation": auto, "vars": vars_, "steps": steps}


def get_automation_graph(name: str) -> Optional[dict[str, Any]]:
    """
    Canonical editor shape for the UI / API.

    Returns:
      {
        "name": str,
        "description": str,
        "created_at": str?,
        "updated_at": str?,
        "compiled_at": str?,
        "compiled_hash": str?,
        "vars": [...],
        "steps": [
          {
            "id": int,
            "step_num": int,
            "label": str,
            "action": str,
            "enabled": int,
            "note": str,
            "params": [...],
            "clauses": [...]
          }
        ]
      }
    """
    full = get_automation_full(name)
    if not full:
        return None

    auto = cast(dict[str, Any], full["automation"])
    vars_ = cast(list[dict[str, Any]], full["vars"])
    steps = cast(list[dict[str, Any]], full["steps"])

    g: dict[str, Any] = {
        "name": auto.get("name", name),
        "description": auto.get("description", "") or "",
        "created_at": auto.get("created_at"),
        "updated_at": auto.get("updated_at"),
        "compiled_at": auto.get("compiled_at"),
        "compiled_hash": auto.get("compiled_hash"),
        "vars": vars_,
        "steps": steps,
    }
    return g


# ============================================================
# Runs (optional metadata)
# ============================================================


def create_run(automation_name: str, container_name: Optional[str] = None, meta_json: str = "") -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO runs(automation_name, container_name, meta_json)
            VALUES(?, ?, ?)
            """,
            (automation_name, container_name, meta_json or ""),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_run(run_id: int, status: str, meta_json: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE runs
               SET status=?,
                   finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                   meta_json=CASE WHEN ? != '' THEN ? ELSE meta_json END
             WHERE id=?
            """,
            (status, meta_json or "", meta_json or "", int(run_id)),
        )
        conn.commit()


# ============================================================
# SAVE GRAPH (the missing core)
# ============================================================

_ALLOWED_VAR_TYPES = {"str", "int", "float", "bool"}

_ALLOWED_HEADS = {"if", "elif", "else"}
_ALLOWED_ACTIONS = {"goto", "continue", "stop", "notify"}
_ALLOWED_STOP_TAGS = {"SUCCESS", "FAILURE", "BREAK"}

_ALLOWED_KINDS = {"buffer", "var", "literal"}

# Keep operators open-ended so schema/sql can enforce. We still guard obvious junk.
_ALLOWED_OPS = {
    "==", "!=", ">", ">=", "<", "<=",
    "contains", "startswith", "endswith", "regex",
}


class SaveGraphError(ValueError):
    pass


def _need_str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    if v is None:
        return ""
    return str(v)


def _need_int(d: dict[str, Any], key: str, default: int = 0) -> int:
    v = d.get(key, default)
    try:
        return int(v)
    except Exception:
        return default


def save_automation_graph(payload: dict[str, Any]) -> None:
    """
    Atomic save of entire automation definition.

    Expected payload shape (host UI can evolve; this is minimum):
      {
        "name": str,
        "description": str,
        "vars": [ { "key": str, "type": "str|int|float|bool", "value": str|num|bool, "description": str? }, ... ],
        "steps": [
          {
            "label": str,
            "action": str,
            "enabled": bool|0|1,
            "note": str?,
            "params": [ { "key": str, "type": "...", "value": ... }, ... ],
            "clauses": [
              {
                "head": "if|elif|else",
                "lhs_kind": "buffer|var|literal" | None,
                "lhs_type": "str|int|float|bool" | None,
                "lhs_value": str | None,
                "op": str | None,
                "rhs_kind": ...,
                "rhs_type": ...,
                "rhs_value": ...,
                "action": "goto|continue|stop|notify",
                "stop_tag": "SUCCESS|FAILURE|BREAK" | None,
                "action_value": str|int|None,
                "note": str?
              }, ...
            ]
          }, ...
        ]
      }

    Rules:
      - step_num is assigned here as 1..N by array order
      - clause_order is assigned here as 0..M by array order
      - var sanitize collisions: FAIL (no auto suffixing)
      - clause var references must exist (after sanitize)
    """
    name = _need_str(payload, "name").strip()
    if not name:
        raise SaveGraphError("name_required")

    description = _need_str(payload, "description").strip()

    vars_in = cast(list[dict[str, Any]], payload.get("vars") or [])
    steps_in = cast(list[dict[str, Any]], payload.get("steps") or [])

    if not steps_in:
        raise SaveGraphError("no_steps")

    # ---- validate vars (sanitize + collision) ----
    seen_sanitized: dict[str, str] = {}
    sanitized_by_original: dict[str, str] = {}

    normalized_vars: list[dict[str, Any]] = []
    for v in vars_in:
        orig_key = _need_str(v, "key").strip()
        if not orig_key:
            raise SaveGraphError("var_key_required")

        typ = _need_str(v, "type").strip()
        if typ not in _ALLOWED_VAR_TYPES:
            raise SaveGraphError(f"bad_var_type:{typ}")

        val = v.get("value")
        # store as TEXT always
        val_text = "" if val is None else str(val)
        desc = _need_str(v, "description")

        san = sanitize_var_name(orig_key)
        if san in seen_sanitized:
            # fail hard (no suffixing)
            raise SaveGraphError(
                f'var_collision_after_sanitize:"{seen_sanitized[san]}" and "{orig_key}" -> "{san}"'
            )

        seen_sanitized[san] = orig_key
        sanitized_by_original[orig_key] = san

        normalized_vars.append(
            {"key": orig_key, "type": typ, "value": val_text, "description": desc}
        )

    # helper: validate var refs in clauses
    def var_exists(var_name: str) -> bool:
        # input could already be sanitized or not; treat as user input and sanitize
        return sanitize_var_name(var_name) in seen_sanitized

    # ---- validate steps + clauses (light validation, DB checks enforce the rest) ----
    normalized_steps: list[dict[str, Any]] = []
    for idx, s in enumerate(steps_in, start=1):
        label = _need_str(s, "label")
        action = _need_str(s, "action").strip()
        if not action:
            raise SaveGraphError(f"step_{idx}_action_required")

        enabled_raw = s.get("enabled", True)
        enabled = bool(int(enabled_raw)) if isinstance(enabled_raw, (int, str)) else bool(enabled_raw)
        note = _need_str(s, "note")

        params_in = cast(list[dict[str, Any]], s.get("params") or [])
        clauses_in = cast(list[dict[str, Any]], s.get("clauses") or [])

        # params validate
        norm_params: list[dict[str, str]] = []
        seen_param_keys: set[str] = set()
        for p in params_in:
            pk = _need_str(p, "key").strip()
            if not pk:
                raise SaveGraphError(f"step_{idx}_param_key_required")
            if pk in seen_param_keys:
                raise SaveGraphError(f"step_{idx}_param_key_duplicate:{pk}")
            seen_param_keys.add(pk)

            pt = _need_str(p, "type").strip()
            if pt not in _ALLOWED_VAR_TYPES:
                raise SaveGraphError(f"step_{idx}_bad_param_type:{pt}")

            pv = p.get("value")
            pv_text = "" if pv is None else str(pv)
            norm_params.append({"key": pk, "type": pt, "value": pv_text})

        # clauses validate
        norm_clauses: list[dict[str, Any]] = []
        for cidx, c in enumerate(clauses_in):
            head = _need_str(c, "head").strip()
            if head not in _ALLOWED_HEADS:
                raise SaveGraphError(f"step_{idx}_bad_clause_head:{head}")

            action_kind = _need_str(c, "action").strip()
            if action_kind not in _ALLOWED_ACTIONS:
                raise SaveGraphError(f"step_{idx}_bad_clause_action:{action_kind}")

            stop_tag = c.get("stop_tag")
            if action_kind == "stop":
                st = str(stop_tag or "").strip()
                if st not in _ALLOWED_STOP_TAGS:
                    raise SaveGraphError(f"step_{idx}_bad_stop_tag:{st}")
            else:
                stop_tag = None

            action_value = c.get("action_value")
            action_value_text = None if action_value is None else str(action_value)

            # predicate fields only required for if/elif
            lhs_kind = c.get("lhs_kind")
            lhs_type = c.get("lhs_type")
            lhs_value = c.get("lhs_value")
            op = c.get("op")
            rhs_kind = c.get("rhs_kind")
            rhs_type = c.get("rhs_type")
            rhs_value = c.get("rhs_value")

            if head in ("if", "elif"):
                lk = str(lhs_kind or "").strip()
                rk = str(rhs_kind or "").strip()
                lt = str(lhs_type or "").strip()
                rt = str(rhs_type or "").strip()
                oo = str(op or "").strip()

                if lk not in _ALLOWED_KINDS or rk not in _ALLOWED_KINDS:
                    raise SaveGraphError(f"step_{idx}_clause_{cidx}_bad_kind")
                if lt not in _ALLOWED_VAR_TYPES or rt not in _ALLOWED_VAR_TYPES:
                    raise SaveGraphError(f"step_{idx}_clause_{cidx}_bad_type")
                if oo not in _ALLOWED_OPS:
                    raise SaveGraphError(f"step_{idx}_clause_{cidx}_bad_op:{oo}")

                # if kind is var -> must exist
                if lk == "var":
                    vv = str(lhs_value or "").strip()
                    if not vv:
                        raise SaveGraphError(f"step_{idx}_clause_{cidx}_lhs_var_missing")
                    if not var_exists(vv):
                        raise SaveGraphError(f'step_{idx}_clause_{cidx}_lhs_var_unknown:"{vv}"')
                if rk == "var":
                    vv = str(rhs_value or "").strip()
                    if not vv:
                        raise SaveGraphError(f"step_{idx}_clause_{cidx}_rhs_var_missing")
                    if not var_exists(vv):
                        raise SaveGraphError(f'step_{idx}_clause_{cidx}_rhs_var_unknown:"{vv}"')

            else:
                # else: predicate fields should be NULL-ish; we just store as None.
                lhs_kind = lhs_type = lhs_value = op = rhs_kind = rhs_type = rhs_value = None

            norm_clauses.append(
                {
                    "head": head,
                    "lhs_kind": None if lhs_kind is None else str(lhs_kind),
                    "lhs_type": None if lhs_type is None else str(lhs_type),
                    "lhs_value": None if lhs_value is None else str(lhs_value),
                    "op": None if op is None else str(op),
                    "rhs_kind": None if rhs_kind is None else str(rhs_kind),
                    "rhs_type": None if rhs_type is None else str(rhs_type),
                    "rhs_value": None if rhs_value is None else str(rhs_value),
                    "action": action_kind,
                    "stop_tag": None if stop_tag is None else str(stop_tag),
                    "action_value": action_value_text,
                    "note": _need_str(c, "note"),
                }
            )

        normalized_steps.append(
            {
                "step_num": idx,
                "label": label,
                "action": action,
                "enabled": 1 if enabled else 0,
                "note": note,
                "params": norm_params,
                "clauses": norm_clauses,
            }
        )

    # ---- Write atomically in one transaction ----
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        try:
            # Upsert base automation
            conn.execute(
                """
                INSERT INTO automations(name, description)
                VALUES(?, ?)
                ON CONFLICT(name) DO UPDATE SET
                  description=excluded.description
                """,
                (name, description),
            )

            # Replace vars + steps graph (CASCADE handles children when steps deleted)
            conn.execute("DELETE FROM automation_vars WHERE automation_name=?", (name,))
            conn.execute("DELETE FROM automation_steps WHERE automation_name=?", (name,))

            # Insert vars
            if normalized_vars:
                conn.executemany(
                    """
                    INSERT INTO automation_vars(automation_name, key, type, value, description)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    [(name, v["key"], v["type"], v["value"], v["description"]) for v in normalized_vars],
                )

            # Insert steps, params, clauses
            for s in normalized_steps:
                cur = conn.execute(
                    """
                    INSERT INTO automation_steps(automation_name, step_num, label, action, enabled, note)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (name, s["step_num"], s["label"], s["action"], s["enabled"], s["note"]),
                )
                step_id = int(cur.lastrowid)

                # params
                params = cast(list[dict[str, str]], s["params"])
                if params:
                    conn.executemany(
                        """
                        INSERT INTO step_params(step_id, key, type, value)
                        VALUES(?, ?, ?, ?)
                        """,
                        [(step_id, p["key"], p["type"], p["value"]) for p in params],
                    )

                # clauses
                clauses = cast(list[dict[str, Any]], s["clauses"])
                for order, c in enumerate(clauses):
                    conn.execute(
                        """
                        INSERT INTO step_clauses(
                          step_id, clause_order, head,
                          lhs_kind, lhs_type, lhs_value,
                          op,
                          rhs_kind, rhs_type, rhs_value,
                          action, stop_tag, action_value,
                          note
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            step_id,
                            int(order),
                            c["head"],
                            c["lhs_kind"],
                            c["lhs_type"],
                            c["lhs_value"],
                            c["op"],
                            c["rhs_kind"],
                            c["rhs_type"],
                            c["rhs_value"],
                            c["action"],
                            c["stop_tag"],
                            c["action_value"],
                            c["note"],
                        ),
                    )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

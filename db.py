from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB_PATH = os.getenv("AUTOMATR_DB_PATH", "./data/automatr.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce FK constraints (SQLite default is OFF per-connection)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def init_db() -> None:
    Path(DEFAULT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.executescript(schema)
        conn.commit()


# ============================================================
# Containers
# ============================================================

def list_containers() -> list[dict[str, Any]]:
    with _connect() as conn:
        has_desc = _has_column(conn, "containers", "description")
        if has_desc:
            rows = conn.execute("SELECT name, description FROM containers ORDER BY name").fetchall()
        else:
            rows = conn.execute("SELECT name FROM containers ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_container(name: str, description: str = "") -> None:
    """
    Backwards compatible:
      - If containers.description exists, store it.
      - Otherwise ignore description.
    """
    with _connect() as conn:
        has_desc = _has_column(conn, "containers", "description")
        if has_desc:
            conn.execute(
                "INSERT INTO containers(name, description) VALUES(?, ?)",
                (name, description or ""),
            )
        else:
            conn.execute(
                "INSERT INTO containers(name) VALUES(?)",
                (name,),
            )
        conn.commit()


def container_exists(name: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM containers WHERE name=?", (name,)).fetchone()
    return row is not None


# ============================================================
# Automations (no YAML)
# ============================================================

def list_automations() -> list[dict[str, Any]]:
    """
    Returns basic list for UI dropdowns.
    """
    with _connect() as conn:
        # updated_at exists in schema.sql we provided (via trigger).
        rows = conn.execute(
            "SELECT name, description, updated_at, compiled_at FROM automations ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_automation(name: str, description: str = "") -> None:
    """
    Creates/updates just the automation metadata.
    Steps/vars/clauses are stored in their own tables.
    """
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
    """
    Returns only the automation row (not steps/vars).
    """
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT name, description, created_at, updated_at, compiled_at, compiled_hash
            FROM automations
            WHERE name=?
            """,
            (name,),
        ).fetchone()
    return dict(row) if row else None


def delete_automation(name: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM automations WHERE name=?", (name,))
        conn.commit()


def set_compiled_script(name: str, compiled_py: str) -> None:
    """
    Stores compiled python script text (optional but useful for export/audit).
    """
    compiled_py = compiled_py or ""
    h = hashlib.sha256(compiled_py.encode("utf-8")).hexdigest() if compiled_py else None
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
    return [dict(r) for r in rows]


def upsert_var(
    automation_name: str,
    key: str,
    type_: str,
    value: str,
    description: str = "",
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO automation_vars(automation_name, key, type, value, description)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(automation_name, key) DO UPDATE SET
              type=excluded.type,
              value=excluded.value,
              description=excluded.description
            """,
            (automation_name, key, type_, str(value), description or ""),
        )
        conn.commit()


def delete_var(automation_name: str, key: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM automation_vars WHERE automation_name=? AND key=?",
            (automation_name, key),
        )
        conn.commit()


# ============================================================
# Steps + params
# ============================================================

def list_steps(automation_name: str) -> list[dict[str, Any]]:
    """
    Returns steps only (no params/clauses).
    """
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
    return [dict(r) for r in rows]


def create_step(
    automation_name: str,
    step_num: int,
    label: str,
    action: str,
    enabled: bool = True,
    note: str = "",
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO automation_steps(automation_name, step_num, label, action, enabled, note)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (automation_name, int(step_num), label or "", action, 1 if enabled else 0, note or ""),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_step(
    step_id: int,
    *,
    step_num: Optional[int] = None,
    label: Optional[str] = None,
    action: Optional[str] = None,
    enabled: Optional[bool] = None,
    note: Optional[str] = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []

    if step_num is not None:
        fields.append("step_num=?")
        values.append(int(step_num))
    if label is not None:
        fields.append("label=?")
        values.append(label)
    if action is not None:
        fields.append("action=?")
        values.append(action)
    if enabled is not None:
        fields.append("enabled=?")
        values.append(1 if enabled else 0)
    if note is not None:
        fields.append("note=?")
        values.append(note)

    if not fields:
        return

    values.append(int(step_id))
    with _connect() as conn:
        conn.execute(
            f"UPDATE automation_steps SET {', '.join(fields)} WHERE id=?",
            tuple(values),
        )
        conn.commit()


def delete_step(step_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM automation_steps WHERE id=?", (int(step_id),))
        conn.commit()


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
    return [dict(r) for r in rows]


def upsert_step_param(step_id: int, key: str, type_: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO step_params(step_id, key, type, value)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(step_id, key) DO UPDATE SET
              type=excluded.type,
              value=excluded.value
            """,
            (int(step_id), key, type_, str(value)),
        )
        conn.commit()


def delete_step_param(step_id: int, key: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM step_params WHERE step_id=? AND key=?",
            (int(step_id), key),
        )
        conn.commit()


# ============================================================
# Clauses (chip rows)
# ============================================================

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
    return [dict(r) for r in rows]


def create_step_clause(
    step_id: int,
    clause_order: int,
    head: str,
    action: str,
    *,
    lhs_kind: Optional[str] = None,
    lhs_type: Optional[str] = None,
    lhs_value: Optional[str] = None,
    op: Optional[str] = None,
    rhs_kind: Optional[str] = None,
    rhs_type: Optional[str] = None,
    rhs_value: Optional[str] = None,
    stop_tag: Optional[str] = None,
    action_value: Optional[str] = None,
    note: str = "",
) -> int:
    with _connect() as conn:
        cur = conn.execute(
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
                int(step_id), int(clause_order), head,
                lhs_kind, lhs_type, lhs_value,
                op,
                rhs_kind, rhs_type, rhs_value,
                action, stop_tag, action_value,
                note or "",
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_step_clause(
    clause_id: int,
    **fields: Any,
) -> None:
    """
    Updates any provided columns on step_clauses.
    Allowed keys: clause_order, head, lhs_kind, lhs_type, lhs_value, op,
                  rhs_kind, rhs_type, rhs_value, action, stop_tag, action_value, note
    """
    allowed = {
        "clause_order", "head",
        "lhs_kind", "lhs_type", "lhs_value",
        "op",
        "rhs_kind", "rhs_type", "rhs_value",
        "action", "stop_tag", "action_value",
        "note",
    }
    sets: list[str] = []
    values: list[Any] = []

    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k}=?")
        values.append(v)

    if not sets:
        return

    values.append(int(clause_id))
    with _connect() as conn:
        conn.execute(
            f"UPDATE step_clauses SET {', '.join(sets)} WHERE id=?",
            tuple(values),
        )
        conn.commit()


def delete_step_clause(clause_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM step_clauses WHERE id=?", (int(clause_id),))
        conn.commit()


# ============================================================
# Convenience: fetch full automation definition for compilation
# ============================================================

def get_automation_full(name: str) -> Optional[dict[str, Any]]:
    """
    Returns:
      {
        automation: {name, description, ...},
        vars: [...],
        steps: [
          {id, step_num, label, action, enabled, note, params:[...], clauses:[...]}
        ]
      }
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

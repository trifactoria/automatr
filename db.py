from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB_PATH = os.getenv("AUTOMATR_DB_PATH", "./data/automatr.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    Path(DEFAULT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.executescript(schema)
        conn.commit()


# ---------------- Containers ----------------
def list_containers() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT name, description FROM containers ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_container(name: str, description: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO containers(name, description) VALUES(?, ?)",
            (name, description or ""),
        )
        conn.commit()


def container_exists(name: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM containers WHERE name=?", (name,)).fetchone()
    return row is not None


# ---------------- Automations ----------------
def list_automations() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name, description, updated_at FROM automations ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_automation(name: str, description: str, yaml_text: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO automations(name, description, yaml, updated_at)
            VALUES(?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(name) DO UPDATE SET
              description=excluded.description,
              yaml=excluded.yaml,
              updated_at=excluded.updated_at
            """,
            (name, description or "", yaml_text or ""),
        )
        conn.commit()


def get_automation(name: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT name, description, yaml, updated_at FROM automations WHERE name=?",
            (name,),
        ).fetchone()
    return dict(row) if row else None


def delete_automation(name: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM automations WHERE name=?", (name,))
        conn.commit()


# ---------------- Executions ----------------
def create_execution(
    container_name: str,
    automation_name: str,
    exec_folder: str,
    status: str,
    run_description: str = "",
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO executions(container_name, automation_name, exec_folder, status, run_description)
            VALUES(?, ?, ?, ?, ?)
            """,
            (container_name, automation_name, exec_folder, status, run_description or ""),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_execution(exec_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE executions
            SET status=?, finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
            WHERE id=?
            """,
            (status, exec_id),
        )
        conn.commit()


def get_running_execution(container_name: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, container_name, automation_name, exec_folder, status, started_at
            FROM executions
            WHERE container_name=? AND status='running'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (container_name,),
        ).fetchone()
    return dict(row) if row else None

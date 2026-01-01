#!/usr/bin/env python3
# bin/export.py

from __future__ import annotations

import os
import re
import sqlite3
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = Path(os.environ.get("AUTOMATR_DB_PATH", "./data/automatr.db")).resolve()
PROJECT_ROOT = Path(os.environ.get("AUTOMATR_PROJECT_ROOT", str(Path.cwd()))).resolve()

# Tracked wrapper (host)
BIN_ACTIONS = (PROJECT_ROOT / "bin" / "automatr_actions.py").resolve()

# Untracked durable scripts (host)
BIN_CONTAINERS_DIR = (PROJECT_ROOT / "bin" / "containers").resolve()

# Untracked container mounts (host)
DATA_DIR = Path(os.environ.get("AUTOMATR_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()


def die(msg: str) -> None:
    print(f"[export] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def snake_case(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "var"
    if s[0].isdigit():
        s = "_" + s
    return s


def bool_literal(text: str) -> str:
    v = (text or "").strip().lower()
    return "True" if v in ("1", "true", "yes", "y", "on") else "False"


def literal_py(typ: str, value: str) -> str:
    if typ == "int":
        return str(int(value))
    if typ == "float":
        return str(float(value))
    if typ == "bool":
        return bool_literal(value)
    return repr("" if value is None else str(value))


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def ensure_symlink(dst: Path, src: Path) -> None:
    ensure_dir(dst.parent)
    if dst.is_symlink() or dst.exists():
        try:
            if dst.is_symlink() and dst.resolve() == src.resolve():
                return
        except Exception:
            pass
        dst.unlink()
    dst.symlink_to(src)


def chmod_exec(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@dataclass
class VarDef:
    original_key: str
    py_name: str
    typ: str
    value: str


def load_vars(conn: sqlite3.Connection, automation: str) -> list[VarDef]:
    rows = conn.execute(
        "SELECT key, type, value FROM automation_vars WHERE automation_name=? ORDER BY key",
        (automation,),
    ).fetchall()

    used: dict[str, str] = {}
    out: list[VarDef] = []
    for r in rows:
        orig = r["key"]
        py = snake_case(orig)
        if py in used:
            die(f'var name collision after sanitize: "{used[py]}" and "{orig}" -> "{py}"')
        used[py] = orig
        out.append(VarDef(original_key=orig, py_name=py, typ=r["type"], value=r["value"]))
    return out


def load_steps(conn: sqlite3.Connection, automation: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT id, step_num, label, action, enabled, note
          FROM automation_steps
         WHERE automation_name=?
         ORDER BY step_num
        """,
        (automation,),
    ).fetchall()

    if not rows:
        die(f'no steps found for automation "{automation}"')

    expected = 1
    for r in rows:
        if int(r["step_num"]) != expected:
            die(f"step numbers must be contiguous 1..N; expected {expected} but saw {r['step_num']}")
        expected += 1

    return rows


def load_params(conn: sqlite3.Connection, step_id: int) -> dict[str, str]:
    rows = conn.execute(
        "SELECT key, type, value FROM step_params WHERE step_id=? ORDER BY key",
        (step_id,),
    ).fetchall()

    params: dict[str, str] = {}
    for r in rows:
        params[r["key"]] = literal_py(r["type"], r["value"])
    return params


def load_clauses(conn: sqlite3.Connection, step_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
          FROM step_clauses
         WHERE step_id=?
         ORDER BY clause_order
        """,
        (step_id,),
    ).fetchall()


def expr_term(kind: str, typ: str, value: Optional[str], varmap_by_py: dict[str, VarDef]) -> str:
    if kind == "buffer":
        return "aa.get_buffer()"
    if kind == "var":
        if not value:
            die("clause var reference missing lhs_value/rhs_value")
        py = snake_case(value)
        if py not in varmap_by_py:
            die(f'clause references var "{value}" (sanitized "{py}") not found in automation_vars')
        return py
    return literal_py(typ, value or "")


def cast_expr(typ: str, expr: str) -> str:
    if typ == "int":
        return f"int({expr})"
    if typ == "float":
        return f"float({expr})"
    if typ == "bool":
        return f"(({expr}).strip().lower() in ('1','true','yes','y','on'))"
    return f"str({expr})"


def predicate_expr(row: sqlite3.Row, varmap_by_py: dict[str, VarDef]) -> str:
    if row["head"] == "else":
        return "True"

    lhs_kind = row["lhs_kind"]
    rhs_kind = row["rhs_kind"]
    op = row["op"]
    lhs_type = row["lhs_type"]
    rhs_type = row["rhs_type"]
    lhs_val = row["lhs_value"]
    rhs_val = row["rhs_value"]

    if not (lhs_kind and rhs_kind and op and lhs_type and rhs_type):
        die("clause predicate fields incomplete for if/elif")

    lhs_raw = expr_term(lhs_kind, lhs_type, lhs_val, varmap_by_py)
    rhs_raw = expr_term(rhs_kind, rhs_type, rhs_val, varmap_by_py)

    lhs = cast_expr(lhs_type, lhs_raw)
    rhs = cast_expr(rhs_type, rhs_raw)

    if op in ("==", "!=", ">", ">=", "<", "<="):
        return f"({lhs} {op} {rhs})"
    if op == "contains":
        return f"({rhs} in {lhs})"
    if op == "startswith":
        return f"({lhs}.startswith({rhs}))"
    if op == "endswith":
        return f"({lhs}.endswith({rhs}))"
    if op == "regex":
        return f"(re.search({rhs}, {lhs}) is not None)"

    die(f"unsupported operator: {op}")
    return "False"


def compile_script_text(
    automation: str, vars_: list[VarDef], steps: list[sqlite3.Row], conn: sqlite3.Connection
) -> str:
    varmap_by_py = {v.py_name: v for v in vars_}

    lines: list[str] = []
    lines.append("#!/usr/bin/env python3")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import re")
    lines.append("import sys")
    lines.append("")
    lines.append("import automatr_actions as aa")
    lines.append("")
    lines.append(f"# automation: {automation}")
    lines.append("")

    if vars_:
        lines.append("# --- automation vars ---")
        for v in vars_:
            lines.append(f"{v.py_name} = {literal_py(v.typ, v.value)}  # {v.original_key}")
        lines.append("")
    else:
        lines.append("# (no vars)")
        lines.append("")

    n_steps = len(steps)
    lines.append(f"_N_STEPS = {n_steps}")
    lines.append("")

    for s in steps:
        step_id = int(s["id"])
        step_num = int(s["step_num"])
        label = (s["label"] or "").strip()
        action = (s["action"] or "").strip()
        enabled = int(s["enabled"]) == 1

        if not action:
            die(f"step {step_num} has empty action")

        params = load_params(conn, step_id)
        clauses = load_clauses(conn, step_id)

        lines.append(f"def step_{step_num}() -> int | None:")
        if label:
            lines.append(f"    # {label}")
        if not enabled:
            lines.append("    # disabled")
            lines.append("    return None")
            lines.append("")
            continue

        # action
        if params:
            kwargs = ", ".join([f"{k}={v}" for k, v in params.items()])
            lines.append(f"    aa.{action}({kwargs})")
        else:
            lines.append(f"    aa.{action}()")

        if clauses:
            lines.append("    # clauses")
            for idx, c in enumerate(clauses):
                head = c["head"]
                pred = predicate_expr(c, varmap_by_py)

                if idx == 0:
                    lines.append(f"    if {pred}:")
                else:
                    if head == "elif":
                        lines.append(f"    elif {pred}:")
                    elif head == "else":
                        lines.append("    else:")
                    else:
                        die("clause chain invalid: 'if' after first clause; use elif/else ordering")

                action_kind = c["action"]
                stop_tag = c["stop_tag"]
                action_value = c["action_value"]

                if action_kind == "goto":
                    if not action_value:
                        die("goto requires action_value (target step num)")
                    tgt = int(action_value)
                    if tgt < 1 or tgt > n_steps:
                        die(f"goto target {tgt} out of range 1..{n_steps}")
                    lines.append(f"        return {tgt}")

                elif action_kind == "continue":
                    lines.append("        return None")

                elif action_kind == "notify":
                    lines.append(f"        aa.notify({repr(action_value or '')})")
                    lines.append("        return None")

                elif action_kind == "stop":
                    if stop_tag not in ("SUCCESS", "FAILURE", "BREAK"):
                        die("stop requires stop_tag SUCCESS|FAILURE|BREAK")
                    msg = action_value or ""
                    if stop_tag == "SUCCESS":
                        lines.append(f"        aa.stop_success({repr(msg)})")
                    elif stop_tag == "FAILURE":
                        lines.append(f"        aa.stop_failure({repr(msg)})")
                    else:
                        lines.append(f"        aa.stop_break({repr(msg)})")
                    lines.append("        return None")

                else:
                    die(f"unsupported clause action: {action_kind}")

            lines.append("")

        lines.append("    return None")
        lines.append("")

    lines.append("def main() -> int:")
    lines.append("    pc = 1")
    lines.append("    while 1 <= pc <= _N_STEPS:")
    lines.append("        aa.check_stop()")
    lines.append("        fn = globals().get(f'step_{pc}')")
    lines.append("        if fn is None:")
    lines.append("            raise RuntimeError(f'missing step function: step_{pc}')")
    lines.append("        nxt = fn()")
    lines.append("        pc = int(nxt) if isinstance(nxt, int) else (pc + 1)")
    lines.append("    return 0")
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    try:")
    lines.append("        raise SystemExit(main())")
    lines.append("    except SystemExit:")
    lines.append("        raise")
    lines.append("    except Exception as e:")
    lines.append("        aa.notify(f'CRASH: {e}', title='AUTOMATR FAILURE')")
    lines.append("        raise")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    # Required CLI: bin/export.py <container> <automation>
    if len(argv) != 3:
        print("usage: bin/export.py <container> <automation>", file=sys.stderr)
        return 2

    container = argv[1].strip()
    automation = argv[2].strip()
    if not container or not automation:
        die("container and automation required")

    if not DEFAULT_DB_PATH.exists():
        die(f"db not found: {DEFAULT_DB_PATH}")

    if not BIN_ACTIONS.exists():
        die(f"missing tracked wrapper: {BIN_ACTIONS}")

    # Durable host target (untracked)
    durable_dir = BIN_CONTAINERS_DIR / container / "bin" / "automations"
    durable_py = durable_dir / f"{automation}.py"

    # Runtime mount root (untracked)
    mount_root = DATA_DIR / container
    mount_bin = mount_root / "bin"

    # Canonical runtime links:
    # data/<container>/bin/automatr_actions.py -> bin/automatr_actions.py
    # data/<container>/bin/<automation> -> bin/containers/<container>/bin/automations/<automation>.py
    runtime_actions = mount_bin / "automatr_actions.py"
    runtime_link = mount_bin / automation

    # Ensure container dirs exist
    ensure_dir(durable_dir)
    ensure_dir(mount_root)
    ensure_dir(mount_bin)
    ensure_dir(mount_root / "logs")
    ensure_dir(mount_root / "queue")
    ensure_dir(mount_root / "pid")
    ensure_dir(mount_root / "config")

    with connect(DEFAULT_DB_PATH) as conn:
        row = conn.execute("SELECT name FROM automations WHERE name=?", (automation,)).fetchone()
        if not row:
            die(f'automation not found: "{automation}"')

        vars_ = load_vars(conn, automation)
        steps = load_steps(conn, automation)
        script = compile_script_text(automation, vars_, steps, conn)

    durable_py.write_text(script, encoding="utf-8")
    chmod_exec(durable_py)

    ensure_symlink(runtime_actions, BIN_ACTIONS)
    ensure_symlink(runtime_link, durable_py)

    print(f"[export] wrote: {durable_py}")
    print(f"[export] linked: {runtime_link} -> {durable_py}")
    print(f"[export] linked: {runtime_actions} -> {BIN_ACTIONS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

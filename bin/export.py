#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ============================================================
# env / paths
# ============================================================

def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


PROJECT_ROOT = Path(get_env("AUTOMATR_PROJECT_ROOT", str(Path.cwd()))).resolve()
DATA_DIR = Path(get_env("AUTOMATR_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
DB_PATH = Path(get_env("AUTOMATR_DB_PATH", str(DATA_DIR / "automatr.db"))).resolve()

BIN_DIR = PROJECT_ROOT / "bin"
BIN_ACTIONS = Path(get_env("AUTOMATR_BIN_ACTIONS", str(BIN_DIR / "automatr_actions.py"))).resolve()
BIN_CONTAINERS_DIR = Path(get_env("AUTOMATR_BIN_CONTAINERS_DIR", str(BIN_DIR / "containers"))).resolve()


# ============================================================
# tiny helpers
# ============================================================

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def chmod_exec(p: Path) -> None:
    try:
        st = p.stat()
        p.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass


def copy_file(src: Path, dst: Path) -> None:
    """Copy file (no symlinks). Avoid SameFileError. Remove legacy symlink dst first."""
    ensure_dir(dst.parent)

    try:
        if dst.is_symlink():
            dst.unlink()
    except FileNotFoundError:
        pass

    try:
        if src.exists() and dst.exists() and src.resolve() == dst.resolve():
            return
    except Exception:
        pass

    shutil.copy2(src, dst)
    chmod_exec(dst)


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def snake(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return ""
    if s[0].isdigit():
        s = "_" + s
    return s.lower()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ============================================================
# export model
# ============================================================

@dataclass
class VarDef:
    key: str
    py_name: str
    typ: str
    value: str
    description: str = ""


def convert_expr(expr: str, typ: str) -> str:
    if typ == "int":
        return f"int({expr})"
    if typ == "float":
        return f"float({expr})"
    if typ == "bool":
        return f"(str({expr}).strip().lower() in ('1','true','yes','y','on'))"
    return f"str({expr})"


def _lit_expr(val: Any, typ: str) -> str:
    s = "" if val is None else str(val)
    if typ == "str":
        return repr(s)
    if typ == "int":
        return f"int({repr(s or '0')})"
    if typ == "float":
        return f"float({repr(s or '0')})"
    if typ == "bool":
        return f"(str({repr(s or 'false')}).strip().lower() in ('1','true','yes','y','on'))"
    return repr(s)


def _resolve_var_pyname(var_name: str, var_by_key: dict[str, VarDef], var_by_py: dict[str, VarDef]) -> str:
    if var_name in var_by_key:
        return var_by_key[var_name].py_name
    sn = snake(var_name)
    if sn and sn in var_by_py:
        return var_by_py[sn].py_name
    raise ValueError(f"unknown_var:{var_name}")


def predicate_expr(row: sqlite3.Row, var_by_key: dict[str, VarDef], var_by_py: dict[str, VarDef]) -> tuple[str, bool]:
    def side(kind: str, typ: str, value: Any) -> tuple[str, bool]:
        needs_re = False
        if kind == "buffer":
            return convert_expr("aa.get_buffer()", typ), needs_re
        if kind == "var":
            py = _resolve_var_pyname(str(value or ""), var_by_key, var_by_py)
            return convert_expr(py, typ), needs_re
        return _lit_expr(value, typ), needs_re

    lhs_kind = row["lhs_kind"] or ""
    lhs_type = row["lhs_type"] or "str"
    lhs_value = row["lhs_value"]

    rhs_kind = row["rhs_kind"] or ""
    rhs_type = row["rhs_type"] or "str"
    rhs_value = row["rhs_value"]

    lhs, needs_re_l = side(lhs_kind, lhs_type, lhs_value)
    rhs, needs_re_r = side(rhs_kind, rhs_type, rhs_value)

    op = row["op"] or ""
    needs_re = needs_re_l or needs_re_r

    allowed = {"==", "!=", ">", "<", ">=", "<=", "contains", "startswith", "endswith", "regex"}
    if op not in allowed:
        raise ValueError(f"bad_op:{op}")

    if op == "contains":
        return f"({rhs} in {lhs})", needs_re
    if op == "startswith":
        return f"(str({lhs}).startswith(str({rhs})))", needs_re
    if op == "endswith":
        return f"(str({lhs}).endswith(str({rhs})))", needs_re
    if op == "regex":
        needs_re = True
        return f"(re.search(str({rhs}), str({lhs})) is not None)", needs_re

    return f"({lhs} {op} {rhs})", needs_re


def _emit_clause_action(lines: list[str], row: sqlite3.Row) -> None:
    act = row["action"]
    actv = row["action_value"] if row["action_value"] is not None else ""
    if act == "goto":
        lines.append(f"        return int({repr(str(actv))})")
    elif act == "continue":
        lines.append("        return None")
    elif act == "notify":
        lines.append(f"        aa.notify({repr(str(actv))})")
        lines.append("        return None")
    elif act == "stop":
        tag = str(row["stop_tag"] or "").upper()
        msg = str(actv)
        if tag == "SUCCESS":
            lines.append(f"        aa.stop_success({repr(msg)})")
        elif tag == "FAILURE":
            lines.append(f"        aa.stop_failure({repr(msg)})")
        else:
            lines.append(f"        aa.stop_break({repr(msg)})")
    else:
        raise ValueError(f"bad_clause_action:{act}")


def compile_script_text(
    automation_name: str,
    vars_: list[VarDef],
    steps: list[dict[str, Any]],
    conn: sqlite3.Connection,
) -> str:
    var_by_key = {v.key: v for v in vars_}
    var_by_py = {v.py_name: v for v in vars_}

    needs_re = False
    for step in steps:
        step_id = int(step["step_id"])
        rows = conn.execute(
            "SELECT * FROM step_clauses WHERE step_id=? ORDER BY clause_order ASC",
            (step_id,),
        ).fetchall()
        for r in rows:
            if (r["op"] or "") == "regex":
                needs_re = True

    lines: list[str] = []
    lines.append("#!/usr/bin/env python3")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import automatr_actions as aa")
    if needs_re:
        lines.append("import re")
    lines.append("")

    # vars
    for v in vars_:
        if v.typ == "str":
            lines.append(f"{v.py_name} = {repr(v.value or '')}")
        elif v.typ == "int":
            lines.append(f"{v.py_name} = int({repr(v.value or '0')})")
        elif v.typ == "float":
            lines.append(f"{v.py_name} = float({repr(v.value or '0')})")
        elif v.typ == "bool":
            lines.append(
                f"{v.py_name} = (str({repr(v.value or 'false')}).strip().lower() in ('1','true','yes','y','on'))"
            )
        else:
            lines.append(f"{v.py_name} = {repr(v.value)}")
    if vars_:
        lines.append("")

    # steps
    for step in steps:
        step_num = int(step["step_num"])
        action = str(step["action"] or "").strip()
        enabled = bool(int(step.get("enabled", 1))) if isinstance(step.get("enabled"), (int, str)) else bool(step.get("enabled", True))

        lines.append(f"def step_{step_num}():")
        lines.append("    aa._check_stop()")

        if not enabled:
            lines.append("    return None")
            lines.append("")
            continue

        # action call
        params = step.get("params") or []
        kwargs: list[str] = []
        for p in params:
            key = str(p["key"])
            typ = str(p["type"])
            val = p["value"]
            if typ == "str":
                kwargs.append(f"{key}={repr(str(val))}")
            elif typ == "int":
                kwargs.append(f"{key}=int({repr(str(val))})")
            elif typ == "float":
                kwargs.append(f"{key}=float({repr(str(val))})")
            elif typ == "bool":
                kwargs.append(f"{key}=(str({repr(str(val))}).strip().lower() in ('1','true','yes','y','on'))")
            else:
                kwargs.append(f"{key}={repr(val)}")

        arg_s = ", ".join(kwargs)
        if not action:
            lines.append("    return None")
            lines.append("")
            continue

        lines.append(f"    aa.{action}({arg_s})" if arg_s else f"    aa.{action}()")

        # clauses
        step_id = int(step["step_id"])
        rows = conn.execute(
            "SELECT * FROM step_clauses WHERE step_id=? ORDER BY clause_order ASC",
            (step_id,),
        ).fetchall()

        if rows:
            has_if = any((r["head"] in ("if", "elif")) for r in rows)

            for row in rows:
                head = row["head"]

                if head == "else":
                    if has_if:
                        # real python else
                        lines.append("    else:")
                        _emit_clause_action(lines, row)
                    else:
                        # IMPORTANT: "else" without any if/elif means unconditional clause
                        # Emit as direct statements (no else:)
                        # Keep indentation consistent with other clause bodies:
                        # We'll emit a one-liner block by temporarily using clause emitter at correct indent.
                        # Easiest: emit a fake 'if True:' block.
                        lines.append("    if True:")
                        _emit_clause_action(lines, row)
                    continue

                pred, _ = predicate_expr(row, var_by_key, var_by_py)
                if head == "if":
                    lines.append(f"    if ({pred}):")
                elif head == "elif":
                    lines.append(f"    elif ({pred}):")
                else:
                    raise ValueError(f"bad_clause_head:{head}")

                _emit_clause_action(lines, row)

        lines.append("    return None")
        lines.append("")

    # main loop
    lines.append("def main() -> int:")
    lines.append("    pc = 1")
    lines.append("    fns = {")
    for step in steps:
        n = int(step["step_num"])
        lines.append(f"        {n}: step_{n},")
    lines.append("    }")
    lines.append("    while pc in fns:")
    lines.append("        aa._check_stop()")
    lines.append("        fn = fns[pc]")
    lines.append("        nxt = fn()")
    lines.append("        if nxt is None:")
    lines.append("            pc += 1")
    lines.append("        else:")
    lines.append("            pc = int(nxt)")
    lines.append("    return 0")
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    raise SystemExit(main())")
    lines.append("")

    return "\n".join(lines)


def _set_compiled_script(conn: sqlite3.Connection, name: str, compiled_py: str) -> None:
    compiled_py = compiled_py or ""
    h = _sha256(compiled_py) if compiled_py else None
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


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: export.py <container> <automation>", file=sys.stderr)
        return 2

    container = argv[1].strip()
    automation = argv[2].strip()

    if not container:
        print("container_required", file=sys.stderr)
        return 2
    if not automation:
        print("automation_required", file=sys.stderr)
        return 2

    durable_dir = BIN_CONTAINERS_DIR / container / "bin" / "automations"
    durable_py = durable_dir / f"{automation}.py"

    mount_root = DATA_DIR / container
    mount_bin = mount_root / "bin"
    runtime_actions = mount_bin / "automatr_actions.py"
    runtime_script = mount_bin / automation

    ensure_dir(durable_dir)
    ensure_dir(mount_bin)
    ensure_dir(mount_root / "logs")
    ensure_dir(mount_root / "queue")
    ensure_dir(mount_root / "pid")
    ensure_dir(mount_root / "config")
    ensure_dir(mount_root / "notify.queue")

    if not DB_PATH.exists():
        print(f"db_not_found:{DB_PATH}", file=sys.stderr)
        return 2

    if not BIN_ACTIONS.exists():
        print(f"automatr_actions_not_found:{BIN_ACTIONS}", file=sys.stderr)
        return 2

    with connect(DB_PATH) as conn:
        arow = conn.execute("SELECT * FROM automations WHERE name=?", (automation,)).fetchone()
        if not arow:
            print(f"automation_not_found:{automation}", file=sys.stderr)
            return 2

        vrows = conn.execute(
            "SELECT key, type, value, description FROM automation_vars WHERE automation_name=? ORDER BY key ASC",
            (automation,),
        ).fetchall()

        vars_: list[VarDef] = []
        seen_py: set[str] = set()
        for vr in vrows:
            key = str(vr["key"])
            py = snake(key)
            if not py:
                print(f"var_empty_after_sanitize:{key}", file=sys.stderr)
                return 2
            if py in seen_py:
                print(f"var_collision_after_sanitize:{key}->{py}", file=sys.stderr)
                return 2
            seen_py.add(py)
            vars_.append(
                VarDef(
                    key=key,
                    py_name=py,
                    typ=str(vr["type"]),
                    value=str(vr["value"] if vr["value"] is not None else ""),
                    description=str(vr["description"] if vr["description"] is not None else ""),
                )
            )

        srows = conn.execute(
            "SELECT id, step_num, label, action, enabled, note FROM automation_steps WHERE automation_name=? ORDER BY step_num ASC",
            (automation,),
        ).fetchall()

        if not srows:
            print(f"no_steps:{automation}", file=sys.stderr)
            return 2

        steps: list[dict[str, Any]] = []
        for sr in srows:
            step_id = int(sr["id"])
            prows = conn.execute(
                "SELECT key, type, value FROM step_params WHERE step_id=? ORDER BY key ASC",
                (step_id,),
            ).fetchall()
            params = [{"key": r["key"], "type": r["type"], "value": r["value"]} for r in prows]

            steps.append(
                {
                    "step_id": step_id,
                    "step_num": int(sr["step_num"]),
                    "label": str(sr["label"] or ""),
                    "action": str(sr["action"] or ""),
                    "enabled": int(sr["enabled"] or 0),
                    "note": str(sr["note"] or ""),
                    "params": params,
                }
            )

        script = compile_script_text(automation, vars_, steps, conn)

        try:
            _set_compiled_script(conn, automation, script)
            conn.commit()
        except Exception:
            conn.rollback()

    durable_py.write_text(script, encoding="utf-8")
    chmod_exec(durable_py)

    copy_file(BIN_ACTIONS, runtime_actions)
    copy_file(durable_py, runtime_script)

    print(f"[export] ok container={container} automation={automation}")
    print(f"[export] durable={durable_py}")
    print(f"[export] runtime_script={runtime_script}")
    print(f"[export] runtime_actions={runtime_actions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

# Mirror runner paths
AUTOMATR_ROOT = Path(os.getenv("AUTOMATR_CONTAINER_ROOT", "/automatr"))
LOGS_DIR = AUTOMATR_ROOT / "logs"
RUN_LOCK = AUTOMATR_ROOT / "run.lock"
STOP_FILE = AUTOMATR_ROOT / "STOP"


@dataclass(frozen=True)
class BotContext:
    node: str
    nick: str
    room: str
    jid: str


# -------------------------
# Parsing + addressing
# -------------------------

def aliases(ctx: BotContext) -> set[str]:
    # In MUC, accept "<node>:" or "<nick>:"
    return {ctx.node, ctx.nick}


def parse_addressed(text: str) -> Tuple[Optional[str], str]:
    """
    "<target>: <rest>" -> (target, rest)
    Otherwise -> (None, original)
    """
    t = (text or "").strip()
    if ":" not in t:
        return None, t
    head, rest = t.split(":", 1)
    target = head.strip()
    rest = rest.strip()
    if not target:
        return None, t
    return target, rest


def extract_backtick_cmd(text: str) -> Optional[str]:
    """
    Accept either:
      `echo test`
    or
      ```bash
      echo test
      ```
    """
    t = (text or "").strip()

    if t.startswith("```") and t.endswith("```"):
        inner = t[3:-3].strip()
        lines = inner.splitlines()
        if not lines:
            return None
        # optional language hint line
        if len(lines) >= 2 and lines[0].strip().isalpha():
            inner2 = "\n".join(lines[1:]).strip()
            return inner2 or None
        return inner or None

    if t.startswith("`") and t.endswith("`") and len(t) >= 2:
        inner = t[1:-1].strip()
        return inner or None

    return None


def clip(s: str, limit: int = 3500) -> str:
    if len(s) <= limit:
        return s
    return s[-limit:]


def tail_file(path: Path, n: int = 80) -> str:
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(size - 65536, 0), 0)
            data = f.read()
        lines = data.splitlines()[-max(n, 1):]
        return b"\n".join(lines).decode("utf-8", errors="replace")
    except FileNotFoundError:
        return "(file missing)"
    except Exception as e:
        return f"(tail error: {e})"


def run_shell(cmd: str, timeout_s: float = 10.0) -> str:
    """
    Run via /bin/sh -lc so shell syntax works.
    Returns combined stdout/stderr, clipped.
    """
    try:
        cp = subprocess.run(
            ["/bin/sh", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        out = (cp.stdout or "") + (cp.stderr or "")
        out = out.strip() or "(no output)"
        if cp.returncode != 0:
            out = f"(exit {cp.returncode})\n{out}"
        return clip(out)
    except subprocess.TimeoutExpired:
        return f"(timeout after {timeout_s}s)"
    except Exception as e:
        return f"(exec error: {e})"


# -------------------------
# Command registry
# -------------------------

CommandFn = Callable[[str, BotContext], str]


def cmd_ping(_arg: str, _ctx: BotContext) -> str:
    return "pong"


def cmd_status(_arg: str, _ctx: BotContext) -> str:
    stop = STOP_FILE.exists()
    lock = RUN_LOCK.read_text().strip() if RUN_LOCK.exists() else "(idle)"
    return f"status stop={stop} lock={lock}"


def cmd_stop(_arg: str, _ctx: BotContext) -> str:
    try:
        STOP_FILE.write_text("STOP\n")
        return "STOP set"
    except Exception as e:
        return f"failed to set STOP: {e}"


def cmd_clear_stop(_arg: str, _ctx: BotContext) -> str:
    try:
        if STOP_FILE.exists():
            STOP_FILE.unlink()
        return "STOP cleared"
    except Exception as e:
        return f"failed to clear STOP: {e}"


def cmd_tail(arg: str, _ctx: BotContext) -> str:
    n = 80
    if arg:
        try:
            n = int(arg.strip())
        except ValueError:
            pass

    files = sorted(LOGS_DIR.glob("*.log"))
    if not files:
        return "no logs yet"

    path = files[-1]
    out = tail_file(path, n=n)
    out = clip(out, 3500)
    return f"tail {path.name}\n{out}"


def cmd_exec(arg: str, _ctx: BotContext) -> str:
    """
    Usage:
      exec echo test
      exec `echo test`
      exec ```bash ... ```
    """
    a = (arg or "").strip()
    if not a:
        return "usage: exec <command>  (or exec `...`)"

    bt = extract_backtick_cmd(a)
    cmd = bt if bt is not None else a
    return run_shell(cmd)


def cmd_help(_arg: str, ctx: BotContext) -> str:
    cmds = ", ".join(sorted({k for k in COMMANDS.keys() if not k.startswith("_")}))
    return (
        "commands: " + cmds + "\n"
        "groupchat: <name>: <cmd> or <nick>: <cmd>\n"
        "dm: just send <cmd> (no prefix)\n"
        "exec: exec echo test | exec `echo test` | `echo test`"
    )


# Keep this central and simple to extend.
COMMANDS: dict[str, CommandFn] = {
    "ping": cmd_ping,
    "status": cmd_status,
    "stop": cmd_stop,
    "clear-stop": cmd_clear_stop,
    "clear_stop": cmd_clear_stop,
    "tail": cmd_tail,
    "exec": cmd_exec,
    "help": cmd_help,
}


def dispatch(cmdline: str, ctx: BotContext) -> str:
    cmdline = (cmdline or "").strip()
    if not cmdline:
        return "no command"

    # bare backticks => implicit exec
    bt = extract_backtick_cmd(cmdline)
    if bt is not None:
        return run_shell(bt)

    # parse first word as command
    try:
        parts = shlex.split(cmdline)
    except ValueError:
        # fallback if quoting is broken
        parts = cmdline.split()

    if not parts:
        return "no command"

    cmd = parts[0].lower()
    arg = cmdline[len(parts[0]):].strip() if len(cmdline) > len(parts[0]) else ""

    fn = COMMANDS.get(cmd)
    if not fn:
        return f"unknown cmd: {cmdline} (try: help)"

    return fn(arg, ctx)


def handle_message(text: str, ctx: BotContext, *, is_direct: bool, is_group: bool) -> Optional[str]:
    """
    Canonical entry point used by working_bot.py.

    - groupchat: require addressing "<target>: <cmd>" where target is node or nick
    - direct message: allow raw commands; addressing also ok
    """
    t = (text or "").strip()
    if not t:
        return None

    target, rest = parse_addressed(t)

    if is_group:
        if target is None:
            return None
        if target not in aliases(ctx):
            return None
        return dispatch(rest, ctx)

    # DM: allow addressed or raw
    if target is not None and target in aliases(ctx):
        return dispatch(rest, ctx)

    return dispatch(t, ctx)


# ---- Compatibility aliases (so future bot code doesn't break) ----

def try_handle_message(text: str, ctx: BotContext) -> Optional[str]:
    # Old naming; assume groupchat style unless caller is explicit elsewhere
    # Kept for compatibility.
    return handle_message(text, ctx, is_direct=False, is_group=True)


def handle(text: str, ctx: BotContext, *, is_direct: bool = False, is_group: bool = True) -> Optional[str]:
    # Another simple alias.
    return handle_message(text, ctx, is_direct=is_direct, is_group=is_group)

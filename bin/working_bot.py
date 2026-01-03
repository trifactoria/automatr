from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# These mirror your runner conventions (and work even if runner isn't imported).
AUTOMATR_ROOT = Path(os.getenv("AUTOMATR_CONTAINER_ROOT", "/automatr"))
AUTOMATR_HOST = Path(os.getenv("AUTOMATR_HOST", "xps"))
LOGS_DIR = AUTOMATR_ROOT / "logs"
RUN_LOCK = AUTOMATR_ROOT / "run.lock"
STOP_FILE = AUTOMATR_ROOT / "STOP"


@dataclass(frozen=True)
class BotContext:
    node: str          # DB/UI name (AUTOMATR_NODE)
    nick: str          # muc nick (agent-<node>)
    room: str          # room jid
    jid: str           # full bound jid


# -------------------------
# Utilities
# -------------------------

def _aliases(ctx: BotContext) -> set[str]:
    # In MUC, accept "<node>:" or "<nick>:"
    return {ctx.node, ctx.nick}


def _parse_addressed(text: str) -> tuple[Optional[str], str]:
    """
    If message starts with "<target>: <rest>", returns (target, rest).
    Otherwise returns (None, original).
    """
    if ":" not in text:
        return None, text.strip()
    head, rest = text.split(":", 1)
    target = head.strip()
    rest = rest.strip()
    if not target:
        return None, text.strip()
    return target, rest


def _tail_file(path: Path, n: int = 80) -> str:
    try:
        with path.open("rb") as f:
            # Simple tail: read last ~64KB (enough for typical logs) then splitlines.
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


def _clip(s: str, limit: int = 3500) -> str:
    if len(s) <= limit:
        return s
    return s[-limit:]


def _extract_backtick_cmd(text: str) -> Optional[str]:
    """
    Accept either:
      `echo test`
    or triple-backtick blocks:
      ```bash
      echo test
      ```
    Returns command string or None.
    """
    t = text.strip()

    # triple backticks
    if t.startswith("```") and t.endswith("```"):
        inner = t[3:-3].strip()
        # allow optional language hint as first token line
        lines = inner.splitlines()
        if not lines:
            return None
        if len(lines) >= 2 and lines[0].strip().isalpha():
            return "\n".join(lines[1:]).strip() or None
        return inner or None

    # single backticks
    if t.startswith("`") and t.endswith("`") and len(t) >= 2:
        inner = t[1:-1].strip()
        return inner or None

    return None


def _run_shell_command(cmd: str, timeout_s: float = 10.0) -> str:
    """
    Runs command using /bin/sh -lc so you can use normal shell syntax.
    Returns combined stdout/stderr.
    """
    try:
        cp = subprocess.run(
            ["/bin/sh", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        out = (cp.stdout or "") + (cp.stderr or "")
        out = out.strip()
        if not out:
            out = "(no output)"
        if cp.returncode != 0:
            out = f"(exit {cp.returncode})\n{out}"
        return _clip(out)
    except subprocess.TimeoutExpired:
        return f"(timeout after {timeout_s}s)"
    except Exception as e:
        return f"(exec error: {e})"


# -------------------------
# Commands
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
    # tail [n]
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
    tail = _tail_file(path, n=n)
    tail = _clip(tail, 3500)
    return f"tail {path.name}\n{tail}"


def cmd_exec(arg: str, _ctx: BotContext) -> str:
    """
    Usage:
      exec echo test
      exec `echo test`
      exec ```bash ... ```
    """
    arg = (arg or "").strip()
    if not arg:
        return "usage: exec <command>  (or exec `...`)"

    bt = _extract_backtick_cmd(arg)
    cmd = bt if bt is not None else arg
    return _run_shell_command(cmd)


def cmd_help(_arg: str, _ctx: BotContext) -> str:
    cmds = ", ".join(sorted(COMMANDS.keys()))
    return (
        "commands: "
        + cmds
        + "\n"
        + "groupchat addressing: <name>: <cmd> OR <nick>: <cmd>\n"
        + "direct message: just send <cmd> (no prefix needed)\n"
        + "exec examples: exec echo test | exec `echo test`"
    )


# Registry: easiest extension path is to add a cmd_* and register it here.
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


def _dispatch(cmdline: str, ctx: BotContext) -> str:
    cmdline = (cmdline or "").strip()
    if not cmdline:
        return "no command"

    # Backticks alone => implicit exec
    bt = _extract_backtick_cmd(cmdline)
    if bt is not None:
        return _run_shell_command(bt)

    parts = shlex.split(cmdline)
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
    Rules:
      - In groupchat: ONLY respond if addressed as "<target>: <cmd>"
        where target is ctx.node or ctx.nick.
      - In direct chat: accept raw commands (no addressing required).
    """
    text = (text or "").strip()
    if not text:
        return None

    target, rest = _parse_addressed(text)

    if is_group:
        if target is None:
            return None
        if target not in _aliases(ctx):
            return None
        return _dispatch(rest, ctx)

    # DM (or non-group): allow either addressed or raw
    if target is not None and target in _aliases(ctx):
        return _dispatch(rest, ctx)

    return _dispatch(text, ctx)

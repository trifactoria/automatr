#!/usr/bin/env python3
"""
automatr_actions.py

Portable action wrapper for Automatr-generated scripts.

Runtime deps (system):
  - xdotool
  - xclip (recommended)
  - notify-send (optional)

Design goals:
  - No JSON/YAML runtime dependencies
  - Deterministic behavior
  - Clipboard buffer is a single global string: `buffer`
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

# Public "copy buffer" used by scripts/conditions.
buffer: str = ""

# If you want slower/faster defaults, change these.
DEFAULT_KEY_DELAY_MS = int(os.environ.get("AUTOMATR_KEY_DELAY_MS", "0"))
DEFAULT_MOUSE_DELAY_MS = int(os.environ.get("AUTOMATR_MOUSE_DELAY_MS", "0"))

# Best-effort DISPLAY support for headless (Xvfb) or real desktop.
DISPLAY = os.environ.get("DISPLAY", "")


class AutomatrError(RuntimeError):
    pass


def _run(cmd: Sequence[str], *, check: bool = True, capture: bool = False, text: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if DISPLAY:
        env["DISPLAY"] = DISPLAY

    try:
        return subprocess.run(
            list(cmd),
            check=check,
            capture_output=capture,
            text=text,
            env=env,
        )
    except FileNotFoundError as e:
        raise AutomatrError(f"Missing required program: {cmd[0]!r}. Install it and retry.") from e
    except subprocess.CalledProcessError as e:
        # Make errors readable.
        out = (e.stdout or "").strip()
        err = (e.stderr or "").strip()
        msg = f"Command failed: {' '.join(map(shlex.quote, cmd))}"
        if out:
            msg += f"\nstdout: {out}"
        if err:
            msg += f"\nstderr: {err}"
        raise AutomatrError(msg) from e


def sleep(seconds: float) -> None:
    time.sleep(float(seconds))


def notify(title: str, message: str = "") -> None:
    """
    Best-effort notification. If notify-send isn't available, silently no-op.
    """
    try:
        _run(["notify-send", str(title), str(message)], check=False, capture=False)
    except AutomatrError:
        return


# -----------------------------
# Mouse / Keyboard primitives
# -----------------------------

def mouse_move(x: int, y: int) -> None:
    if DEFAULT_MOUSE_DELAY_MS:
        _run(["xdotool", "mousemove", "--sync", str(int(x)), str(int(y))])
        _run(["xdotool", "sleep", str(DEFAULT_MOUSE_DELAY_MS / 1000.0)], check=False)
    else:
        _run(["xdotool", "mousemove", "--sync", str(int(x)), str(int(y))])


def click(button: Union[int, str] = 1, *, repeat: int = 1, delay_ms: int = 0) -> None:
    """
    button: 1=left, 2=middle, 3=right, 4=scroll up, 5=scroll down
    """
    args = ["xdotool", "click"]
    if delay_ms:
        args += ["--delay", str(int(delay_ms))]
    if repeat and repeat != 1:
        args += ["--repeat", str(int(repeat))]
    args += [str(button)]
    _run(args)


def key(keys: str) -> None:
    """
    Example: key("ctrl+c") or key("Return")
    """
    args = ["xdotool", "key"]
    if DEFAULT_KEY_DELAY_MS:
        args += ["--delay", str(DEFAULT_KEY_DELAY_MS)]
    args += [keys]
    _run(args)


def type_text(text: str) -> None:
    """
    Types text at current focus. Uses xdotool type for natural behavior.
    """
    args = ["xdotool", "type"]
    if DEFAULT_KEY_DELAY_MS:
        args += ["--delay", str(DEFAULT_KEY_DELAY_MS)]
    args += ["--", str(text)]
    _run(args)


def paste_text(text: str) -> None:
    """
    Writes text to clipboard and pastes via ctrl+v.
    """
    write_clipboard(text)
    key("ctrl+v")


def drag(start_x: int, start_y: int, end_x: int, end_y: int, *, button: int = 1) -> None:
    """
    Mouse drag using mousedown/mouseup.
    """
    mouse_move(start_x, start_y)
    _run(["xdotool", "mousedown", str(int(button))])
    mouse_move(end_x, end_y)
    _run(["xdotool", "mouseup", str(int(button))])


# -----------------------------
# Clipboard helpers (buffer)
# -----------------------------

def read_clipboard(*, selection: str = "clipboard") -> str:
    """
    Reads the clipboard using xclip.
    selection: 'clipboard' (default) or 'primary'
    """
    # xclip -selection clipboard -o
    cp = _run(["xclip", "-selection", selection, "-o"], capture=True)
    txt = (cp.stdout or "")
    # Always normalize minimally.
    return txt.strip()


def write_clipboard(text: str, *, selection: str = "clipboard") -> None:
    """
    Writes to clipboard using xclip.
    """
    # xclip -selection clipboard -i
    env = os.environ.copy()
    if DISPLAY:
        env["DISPLAY"] = DISPLAY
    try:
        p = subprocess.Popen(
            ["xclip", "-selection", selection, "-i"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
        )
    except FileNotFoundError as e:
        raise AutomatrError("Missing required program 'xclip'. Install it and retry.") from e

    assert p.stdin is not None
    p.stdin.write(str(text))
    p.stdin.close()
    rc = p.wait()
    if rc != 0:
        raise AutomatrError(f"xclip write failed (rc={rc})")


def copy() -> str:
    """
    Sends ctrl+c and updates global buffer from clipboard.
    """
    global buffer
    key("ctrl+c")
    # Small settle time helps some UIs.
    time.sleep(0.05)
    buffer = read_clipboard()
    return buffer


def dragcopy(start_x: int, start_y: int, end_x: int, end_y: int, *, button: int = 1) -> str:
    """
    Drag-select region and copy to clipboard; updates global buffer.
    """
    global buffer
    drag(start_x, start_y, end_x, end_y, button=button)
    return copy()


# -----------------------------
# Parsing helpers (buffer → types)
# -----------------------------

def buffer_str() -> str:
    return str(buffer)


def buffer_int(*, default: Optional[int] = None) -> int:
    s = str(buffer).strip()
    # Common cleanup: remove commas and dollar signs.
    s = s.replace(",", "").replace("$", "")
    try:
        return int(s)
    except Exception:
        if default is not None:
            return int(default)
        raise AutomatrError(f"buffer is not int-parsable: {buffer!r}")


def buffer_float(*, default: Optional[float] = None) -> float:
    s = str(buffer).strip()
    s = s.replace(",", "").replace("$", "")
    try:
        return float(s)
    except Exception:
        if default is not None:
            return float(default)
        raise AutomatrError(f"buffer is not float-parsable: {buffer!r}")


# -----------------------------
# Screenshot (optional)
# -----------------------------

def screenshot(path: str) -> None:
    """
    Saves a screenshot to the given path using scrot.
    """
    _run(["scrot", str(path)])

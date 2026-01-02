#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

# Container mount root is /automatr
AUTOMATR_ROOT = Path(os.environ.get("AUTOMATR_CONTAINER_ROOT", "/automatr"))
STOP_FILE = AUTOMATR_ROOT / "STOP"

# Best-effort clipboard tool. Prefer xclip; xsel could be added later.
XCLIP = os.environ.get("AUTOMATR_XCLIP_BIN", "xclip")
XDOTOOL = os.environ.get("AUTOMATR_XDOTOOL_BIN", "xdotool")

# Host notification queue (lives inside /automatr which is a bind-mount)
NOTIFY_QUEUE_DIR = Path(os.environ.get("AUTOMATR_NOTIFY_QUEUE_DIR", str(AUTOMATR_ROOT / "notify.queue")))

# A shared in-process buffer, updated by dragcopy/copy actions
_buffer: str = ""


class AutomatrStopped(SystemExit):
    """Raised when STOP file is present."""
    pass


def _check_stop() -> None:
    # Existence-only latch. Empty file is fine.
    if STOP_FILE.exists():
        raise AutomatrStopped("STOP file present")


def _run(argv: list[str], *, check: bool = True, capture: bool = False, text: bool = True) -> subprocess.CompletedProcess:
    _check_stop()
    return subprocess.run(
        argv,
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=text,
    )


def notify(msg: str, title: str = "AUTOMATR") -> None:
    """
    Host notification:
    - DO NOT call notify-send in the container.
    - Enqueue a small text file in /automatr/notify.queue.
    Host-side app.py consumes it and runs notify-send.
    """
    _check_stop()
    try:
        NOTIFY_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        path = NOTIFY_QUEUE_DIR / f"notify-{ts}.txt"
        # format: first line title, second line message
        path.write_text(f"{title}\n{str(msg)}\n", encoding="utf-8")
    except Exception:
        # never crash automation over notifications
        pass


def sleep(seconds: float) -> None:
    _check_stop()
    time.sleep(float(seconds))


def set_buffer(value: str) -> None:
    global _buffer
    _buffer = "" if value is None else str(value)


def get_buffer() -> str:
    return _buffer


def _clipboard_set(text: str) -> None:
    _check_stop()
    # Feed stdin to xclip
    p = subprocess.Popen(
        [XCLIP, "-selection", "clipboard"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert p.stdin is not None
        p.stdin.write((text or "").encode("utf-8"))
        p.stdin.close()
        p.wait(timeout=2)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _clipboard_get() -> str:
    cp = _run([XCLIP, "-selection", "clipboard", "-o"], capture=True, check=False)
    out = (cp.stdout or "").strip()
    return out


def mouse_move(x: int, y: int) -> None:
    _run([XDOTOOL, "mousemove", str(int(x)), str(int(y))])


def click(button: int = 1) -> None:
    _run([XDOTOOL, "click", str(int(button))])


def key(keys: str) -> None:
    _run([XDOTOOL, "key", str(keys)])


def type_text(text: str, delay_ms: int = 0) -> None:
    argv = [XDOTOOL, "type"]
    if delay_ms and int(delay_ms) > 0:
        argv += ["--delay", str(int(delay_ms))]
    argv += ["--", str(text)]
    _run(argv)


def drag(start_x: int, start_y: int, end_x: int, end_y: int, button: int = 1) -> None:
    _run([XDOTOOL, "mousemove", str(int(start_x)), str(int(start_y))])
    _run([XDOTOOL, "mousedown", str(int(button))])
    _run([XDOTOOL, "mousemove", str(int(end_x)), str(int(end_y))])
    _run([XDOTOOL, "mouseup", str(int(button))])


def dragcopy(start_x: int, start_y: int, end_x: int, end_y: int, button: int = 1) -> str:
    """
    Drag-select region, copy (ctrl+c), read clipboard into buffer.
    Assumes the UI supports drag selection and ctrl+c copies selected text.
    """
    _check_stop()
    drag(start_x, start_y, end_x, end_y, button=button)
    sleep(0.05)
    key("ctrl+c")
    sleep(0.05)
    txt = _clipboard_get()
    set_buffer(txt)
    return txt


def stop_success(msg: str) -> None:
    notify(str(msg), title="AUTOMATR SUCCESS")
    raise SystemExit(0)


def stop_failure(msg: str) -> None:
    notify(str(msg), title="AUTOMATR FAILURE")
    raise SystemExit(2)


def stop_break(msg: str) -> None:
    notify(str(msg), title="AUTOMATR BREAK")
    raise SystemExit(3)

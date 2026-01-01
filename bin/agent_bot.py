#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import slixmpp


# ---------------- Logging ----------------
LOGLEVEL = os.getenv("AUTOMATR_XMPP_LOGLEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOGLEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("slixmpp").setLevel(getattr(logging, LOGLEVEL, logging.INFO))


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------- Paths ----------------
AUTOMATR_ROOT = Path(os.getenv("AUTOMATR_ROOT", "/automatr"))
EVENTS_DIR = Path(os.getenv("AUTOMATR_EVENTS_DIR", str(AUTOMATR_ROOT / "events.queue")))
STOP_FILE = Path(os.getenv("AUTOMATR_STOP_FILE", str(AUTOMATR_ROOT / "STOP")))
RUN_LOCK = Path(os.getenv("AUTOMATR_RUN_LOCK", str(AUTOMATR_ROOT / "run.lock")))
LOGS_DIR = Path(os.getenv("AUTOMATR_LOGS_DIR", str(AUTOMATR_ROOT / "logs")))

# ---------------- XMPP env ----------------
XMPP_DOMAIN = os.getenv("AUTOMATR_XMPP_DOMAIN", "automatr-xmpp.local")
XMPP_HOST = os.getenv("AUTOMATR_XMPP_HOST", "automatr-prosody")
XMPP_PORT = int(os.getenv("AUTOMATR_XMPP_PORT", "5222"))
XMPP_PASSWORD = os.getenv("AUTOMATR_XMPP_PASSWORD", "")

INSECURE_TLS = os.getenv("AUTOMATR_XMPP_INSECURE_TLS", "0").lower() in ("1", "true", "yes", "on")

MUC_ROOM = os.getenv("AUTOMATR_XMPP_MUC", f"automatr@conference.{XMPP_DOMAIN}")
MUC_NICK_PREFIX = os.getenv("AUTOMATR_XMPP_NICK_PREFIX", "agent-")

NODE = os.getenv("AUTOMATR_NODE") or socket.gethostname()
AGENT_USER = os.getenv("AUTOMATR_XMPP_USER", f"{MUC_NICK_PREFIX}{NODE}")
AGENT_JID = os.getenv("AUTOMATR_XMPP_JID", f"{AGENT_USER}@{XMPP_DOMAIN}")

CMD_PREFIX = f"{AGENT_USER}:"


def tcp_check(host: str, port: int, timeout: float = 1.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "ok"
    except Exception as e:
        return False, str(e)


@dataclass
class Event:
    path: Path
    payload: dict


def _safe_read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _tail_file(path: Path, n: int = 80) -> str:
    try:
        lines = path.read_text(errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except FileNotFoundError:
        return f"(missing: {path})"
    except Exception as e:
        return f"(error reading {path}: {e})"


class AgentBot(slixmpp.ClientXMPP):
    def __init__(self, jid: str, password: str):
        super().__init__(jid, password)

        self.nick = AGENT_USER
        self.room = MUC_ROOM

        self.event_q: "queue.Queue[Event]" = queue.Queue()
        self._stop_evt = threading.Event()

        # Required plugins
        self.register_plugin("xep_0030")  # disco
        self.register_plugin("xep_0045")  # muc
        try:
            self.register_plugin("xep_0199")  # ping
        except Exception:
            pass

        # High-signal visibility hooks
        self.add_event_handler("connecting", lambda e: log("[agent_bot] event: connecting"))
        self.add_event_handler("connected", lambda e: log("[agent_bot] event: connected (tcp)"))
        self.add_event_handler("connection_failed", lambda e: log("[agent_bot] event: connection_failed"))
        self.add_event_handler("disconnected", lambda e: log("[agent_bot] event: disconnected"))
        self.add_event_handler("session_start", self.on_session_start)

        # Auth failures
        self.add_event_handler("failed_auth", lambda e: log("[agent_bot] AUTH FAILED (failed_auth)"))
        self.add_event_handler("auth_failed", lambda e: log("[agent_bot] AUTH FAILED (auth_failed)"))

        # Messages
        self.add_event_handler("groupchat_message", self.on_groupchat_message)

    async def on_session_start(self, _event):
        log("[agent_bot] session_start")
        self.send_presence()

        try:
            await self.get_roster()
        except Exception as e:
            log(f"[agent_bot] get_roster error: {e}")

        try:
            self.plugin["xep_0045"].join_muc(self.room, self.nick, wait=True)
            log(f"[agent_bot] joined muc {self.room} as {self.nick}")
        except Exception as e:
            log(f"[agent_bot] join_muc failed: {e}")

        try:
            self.send_message(mto=self.room, mtype="groupchat", mbody=f"[{AGENT_USER}] online")
            log("[agent_bot] announced online")
        except Exception as e:
            log(f"[agent_bot] send online failed: {e}")

        threading.Thread(target=self._event_watcher_loop, daemon=True).start()
        threading.Thread(target=self._event_sender_loop, daemon=True).start()

    def on_groupchat_message(self, msg):
        body = (msg.get("body") or "").strip()
        if not body:
            return
        if msg.get("mucnick") == self.nick:
            return
        if not body.lower().startswith(CMD_PREFIX.lower()):
            return

        cmd = body[len(CMD_PREFIX):].strip()
        if not cmd:
            return

        resp = self._handle_command(cmd)
        if resp:
            self.send_message(mto=self.room, mtype="groupchat", mbody=f"[{AGENT_USER}] {resp}")

    def _handle_command(self, cmd: str) -> str:
        cmd_l = cmd.lower()

        if cmd_l == "ping":
            return "pong"

        if cmd_l == "status":
            stop = STOP_FILE.exists()
            lock = RUN_LOCK.read_text().strip() if RUN_LOCK.exists() else "(idle)"
            return f"status stop={stop} lock={lock}"

        if cmd_l.startswith("stop"):
            try:
                STOP_FILE.write_text("STOP\n")
                return "STOP set"
            except Exception as e:
                return f"failed to set STOP: {e}"

        if cmd_l in ("clear-stop", "clear_stop"):
            try:
                if STOP_FILE.exists():
                    STOP_FILE.unlink()
                return "STOP cleared"
            except Exception as e:
                return f"failed to clear STOP: {e}"

        if cmd_l.startswith("tail"):
            parts = cmd.split()
            n = 80
            if len(parts) > 1:
                try:
                    n = int(parts[1])
                except ValueError:
                    pass

            files = sorted(LOGS_DIR.glob("*.log"))
            if not files:
                return "no logs yet"
            tail = _tail_file(files[-1], n=n)
            if len(tail) > 3500:
                tail = tail[-3500:]
            return f"tail {files[-1].name}\n{tail}"

        return f"unknown cmd: {cmd}"

    def _event_watcher_loop(self):
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        while not self._stop_evt.is_set():
            try:
                for p in sorted(EVENTS_DIR.glob("*.json")):
                    payload = _safe_read_json(p)
                    if payload is None:
                        try:
                            p.rename(p.with_suffix(".bad"))
                        except Exception:
                            pass
                        continue
                    self.event_q.put(Event(path=p, payload=payload))
                time.sleep(0.25)
            except Exception:
                time.sleep(0.5)

    def _event_sender_loop(self):
        while not self._stop_evt.is_set():
            try:
                ev = self.event_q.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                kind = ev.payload.get("type", "event")
                msg = ev.payload.get("msg") or ""
                ts = ev.payload.get("ts") or ""
                body = f"[{AGENT_USER}] {kind} {ts} {msg}".strip()
                self.send_message(mto=self.room, mtype="groupchat", mbody=body)
                try:
                    ev.path.unlink()
                except FileNotFoundError:
                    pass
            except Exception as e:
                log(f"[agent_bot] event send error: {e}")
                time.sleep(0.5)


def _apply_insecure_tls_for_starttls(xmpp: slixmpp.ClientXMPP) -> None:
    if not INSECURE_TLS:
        return
    log("[agent_bot] WARNING: insecure TLS enabled (skip cert verification during STARTTLS)")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    xmpp.ssl_context = ctx  # used for STARTTLS too


async def amain() -> int:
    if not XMPP_PASSWORD:
        log("[agent_bot] AUTOMATR_XMPP_PASSWORD is required")
        return 2

    ok, why = tcp_check(XMPP_HOST, XMPP_PORT, timeout=1.0)
    if not ok:
        log(f"[agent_bot] tcp check failed {XMPP_HOST}:{XMPP_PORT} -> {why}")
        return 10

    # Resolve endpoint for stability, but keep JID domain intact.
    endpoint_ip = XMPP_HOST
    try:
        endpoint_ip = socket.gethostbyname(XMPP_HOST)
    except Exception:
        pass

    log(
        f"[agent_bot] starting jid={AGENT_JID} room={MUC_ROOM} "
        f"endpoint={endpoint_ip}:{XMPP_PORT} insecure_tls={INSECURE_TLS}"
    )

    xmpp = AgentBot(AGENT_JID, XMPP_PASSWORD)

    # CRITICAL: 5222 is plaintext + STARTTLS. Do NOT use direct TLS.
    xmpp.use_ssl = False   # no direct TLS on connect
    xmpp.use_tls = True    # do STARTTLS upgrade if offered

    _apply_insecure_tls_for_starttls(xmpp)

    try:
        connected = await xmpp.connect(host=endpoint_ip, port=XMPP_PORT)
    except Exception as e:
        log(f"[agent_bot] connect exception: {e}")
        return 3

    if not connected:
        log("[agent_bot] connect returned False")
        return 4

    log("[agent_bot] connected; waiting for disconnect (bot is running)")
    await xmpp.disconnected
    return 0


def main() -> int:
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

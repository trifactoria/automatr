#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import ssl
import sys
from dataclasses import dataclass


# ----------------------------
# Helpers
# ----------------------------

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _default_domain() -> str:
    return (os.getenv("AUTOMATR_XMPP_DOMAIN") or "xps.local").strip()


def _default_muc(domain: str) -> str:
    return (os.getenv("AUTOMATR_XMPP_MUC") or f"automatr@conference.{domain}").strip()


def _default_password() -> str:
    return (os.getenv("AUTOMATR_XMPP_PASSWORD") or "supersecret").strip()


def _default_host() -> str:
    return (os.getenv("AUTOMATR_XMPP_HOST") or "automatr-prosody").strip()


def _default_port() -> int:
    try:
        return int((os.getenv("AUTOMATR_XMPP_PORT") or "5222").strip())
    except ValueError:
        return 5222


def _derive_agent_identity(domain: str) -> tuple[str, str, str]:
    """
    Returns (jid, username_localpart, nick)

    HARD RULES:
      - If AUTOMATR_AGENT_JID is set, use it.
      - Else if AUTOMATR_AGENT_NAME is set, use it as localpart.
      - Else derive from AUTOMATR_CONTAINER_NAME (preferred) then AUTOMATR_NODE.
      - If none are set, force 'something-broke' to make it obvious.
    """
    # 1) explicit JID
    agent_jid = (os.getenv("AUTOMATR_AGENT_JID") or "").strip()
    if agent_jid:
        localpart = agent_jid.split("@", 1)[0]
        nick = localpart
        return agent_jid, localpart, nick

    # 2) explicit localpart
    agent_name = (os.getenv("AUTOMATR_AGENT_NAME") or "").strip()
    if agent_name:
        jid = f"{agent_name}@{domain}"
        nick = agent_name
        return jid, agent_name, nick

    # 3) derive from orchestrator-provided container/node name
    container_name = (os.getenv("AUTOMATR_CONTAINER_NAME") or "").strip()
    node = (os.getenv("AUTOMATR_NODE") or "").strip()

    base = container_name or node or "something-broke"
    agent_name = f"agent-{base}"
    jid = f"{agent_name}@{domain}"
    nick = agent_name
    return jid, agent_name, nick


def make_ssl_context(insecure: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ----------------------------
# Config
# ----------------------------

@dataclass(frozen=True)
class Cfg:
    domain: str
    muc: str
    host: str
    port: int
    jid: str          # full JID
    username: str     # localpart
    password: str
    nick: str
    insecure_tls: bool
    register: bool


def load_cfg() -> Cfg:
    domain = _default_domain()
    jid, username, nick = _derive_agent_identity(domain)
    return Cfg(
        domain=domain,
        muc=_default_muc(domain),
        host=_default_host(),
        port=_default_port(),
        jid=jid,
        username=username,
        password=_default_password(),
        nick=nick,
        insecure_tls=_env_bool("AUTOMATR_XMPP_INSECURE_TLS", default=False),
        register=_env_bool("AUTOMATR_XMPP_REGISTER", default=False),
    )


# ----------------------------
# XMPP Bot (slixmpp 1.10.0)
# ----------------------------

import slixmpp
from slixmpp import ClientXMPP


class AgentBot(ClientXMPP):
    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        super().__init__(cfg.jid, cfg.password)

        # STARTTLS wrapping
        self.ssl_context = make_ssl_context(cfg.insecure_tls)

        # State flags
        self._ready = asyncio.Event()
        self._disconnected = asyncio.Event()

        # Registration gating
        self._want_register = cfg.register
        self._reconnect_after_register = False

        # Plugins
        self.register_plugin("xep_0030")  # Service discovery
        self.register_plugin("xep_0199")  # Ping
        self.register_plugin("xep_0045")  # MUC
        self.register_plugin("xep_0077")  # In-band registration (optional)

        # Events
        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("disconnected", self.on_disconnected)
        self.add_event_handler("connection_failed", self.on_connection_failed)
        self.add_event_handler("register", self.on_register)

        self.client_name = "automatr-agent"

    async def on_register(self, _event):
        """
        Only register if AUTOMATR_XMPP_REGISTER=1.
        If already exists (conflict), continue normal auth.
        """
        if not self._want_register:
            logging.warning("register event fired but _want_register is false; ignoring")
            return

        try:
            logging.warning("attempting in-band registration for %s", self.cfg.jid)
            await self["xep_0077"].register(self.cfg.username, self.cfg.password)
            logging.warning("registration succeeded; will reconnect to login cleanly")
            self._reconnect_after_register = True
            self.disconnect()
        except Exception as e:
            msg = str(e).lower()
            if "conflict" in msg or "already" in msg or "exists" in msg:
                logging.warning("in-band registration: already exists; proceeding to login")
                self._want_register = False
                return
            logging.exception("in-band registration failed; proceeding to login anyway")
            self._want_register = False

    async def on_session_start(self, _event):
        try:
            logging.info("session_start jid=%s", self.boundjid.bare)

            self.send_presence()
            try:
                await self.get_roster()
            except Exception:
                pass

            # Join MUC
            self.plugin["xep_0045"].join_muc(self.cfg.muc, self.cfg.nick)
            logging.info("join_muc sent room=%s nick=%s", self.cfg.muc, self.cfg.nick)

            self._ready.set()
        except Exception:
            logging.exception("session_start failed")
            self.disconnect()

    def on_connection_failed(self, _event):
        logging.warning("connection_failed")
        self._disconnected.set()

    def on_disconnected(self, _event):
        logging.warning("disconnected")
        self._disconnected.set()


async def run_once(cfg: Cfg) -> int:
    """
    Return codes:
      0 = connected + joined room
      1 = failed before ready
      2 = registration succeeded and we should retry (reconnect)
    """
    xmpp = AgentBot(cfg)

    connect_sig = inspect.signature(xmpp.connect)
    logging.info(
        "connecting jid=%s host=%s port=%d room=%s insecure_tls=%s register=%s (connect sig=%s)",
        xmpp.boundjid.bare, cfg.host, cfg.port, cfg.muc, cfg.insecure_tls, cfg.register, connect_sig
    )

    fut = xmpp.connect(host=cfg.host, port=cfg.port)
    ok = await fut
    if not ok:
        return 1

    ready_task = asyncio.create_task(xmpp._ready.wait())
    disc_task = asyncio.create_task(xmpp._disconnected.wait())
    done, pending = await asyncio.wait({ready_task, disc_task}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    if xmpp._reconnect_after_register:
        return 2
    if xmpp._ready.is_set():
        return 0
    return 1


async def amain() -> int:
    cfg = load_cfg()

    # Log the resolved identity up front (this is what you care about)
    logging.info("resolved identity: jid=%s username=%s nick=%s domain=%s",
                 cfg.jid, cfg.username, cfg.nick, cfg.domain)

    backoff = 1.0
    while True:
        try:
            rc = await run_once(cfg)
        except Exception:
            logging.exception("bot crashed; restarting")
            rc = 1

        if rc == 0:
            logging.info("bot is ready (joined room). staying alive.")
            backoff = 1.0
            await asyncio.sleep(3600)
            continue

        if rc == 2:
            await asyncio.sleep(0.5)
            continue

        logging.warning("bot exited with code=%s; sleeping %.1fs then retry", rc, backoff)
        await asyncio.sleep(backoff)
        backoff = min(8.0, backoff * 1.6)


def main() -> int:
    logging.basicConfig(
        level=os.getenv("AUTOMATR_XMPP_LOGLEVEL", "DEBUG").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.info("slixmpp %s", getattr(slixmpp, "__version__", "unknown"))
    logging.info("ClientXMPP has process: %s", hasattr(ClientXMPP, "process"))
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())

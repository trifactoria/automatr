#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import socket
import ssl
import sys
from dataclasses import dataclass
from typing import Any, Dict, Tuple

import slixmpp


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None:
        raise SystemExit(f"Missing required env var: {name}")
    return v


@dataclass
class Cfg:
    domain: str
    host: str
    port: int
    password: str
    room: str
    nick: str
    insecure_tls: bool


def load_cfg() -> Cfg:
    domain = env("AUTOMATR_XMPP_DOMAIN", "automatr-xmpp.local")
    host = env("AUTOMATR_XMPP_HOST", "automatr-prosody")
    port = int(env("AUTOMATR_XMPP_PORT", "5222"))
    password = env("AUTOMATR_XMPP_PASSWORD", "supersecret")
    room = env("AUTOMATR_XMPP_MUC", f"automatr@conference.{domain}")
    nick = os.getenv("AUTOMATR_AGENT_NAME") or os.getenv("HOSTNAME") or "agent"
    insecure_tls = env("AUTOMATR_XMPP_INSECURE_TLS", "0").lower() in ("1", "true", "yes", "on")
    return Cfg(domain=domain, host=host, port=port, password=password, room=room, nick=nick, insecure_tls=insecure_tls)


def resolve_ipv4(name: str) -> str:
    return socket.gethostbyname(name)


def make_ssl_context(insecure: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


class AgentBot(slixmpp.ClientXMPP):
    def __init__(self, cfg: Cfg):
        jid = f"agent-tests@{cfg.domain}"
        super().__init__(jid, cfg.password)
        self.cfg = cfg
        self._hello_sent = asyncio.Event()

        # These attributes exist in many builds; set them anyway.
        # The key is ALSO forcing use_ssl=False in connect() below.
        self.use_ssl = False          # never implicit TLS on 5222
        self.use_tls = True           # allow STARTTLS
        self.disable_starttls = False

        self.ssl_context = make_ssl_context(cfg.insecure_tls)

        self.register_plugin("xep_0030")  # disco
        self.register_plugin("xep_0199")  # ping
        self.register_plugin("xep_0045")  # muc

        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("connection_failed", self.on_connection_failed)
        self.add_event_handler("disconnected", self.on_disconnected)

    async def on_session_start(self, _event):
        logging.info("session_start: sending presence + joining room")
        self.send_presence()
        try:
            await self.get_roster()
        except Exception:
            # roster isn't critical for our smoke test
            logging.debug("get_roster failed (ignored)", exc_info=True)

        # Join the MUC and say hi
        self.plugin["xep_0045"].join_muc(self.cfg.room, self.cfg.nick)

        await asyncio.sleep(0.75)
        self.send_message(
            mto=self.cfg.room,
            mbody=f"hello from agent {self.cfg.nick}",
            mtype="groupchat",
        )
        logging.info("sent hello to %s", self.cfg.room)
        self._hello_sent.set()

        # Disconnect cleanly so the container doesn't spam reconnect loops
        await asyncio.sleep(0.25)
        self.disconnect()

    def on_connection_failed(self, _event):
        logging.error("connection_failed")

    def on_disconnected(self, _event):
        logging.warning("disconnected")


async def maybe_await(x: Any) -> Any:
    if inspect.isawaitable(x):
        return await x
    return x


def build_connect_call(xmpp: AgentBot, ip: str, port: int) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    """
    Introspect slixmpp ClientXMPP.connect signature and build the correct call.
    We MUST force use_ssl=False so we do NOT send TLS-first bytes to 5222.
    """
    sig = inspect.signature(xmpp.connect)
    params = sig.parameters

    logging.info("slixmpp.connect signature: %s", sig)

    kwargs: Dict[str, Any] = {}

    # Force plaintext + STARTTLS behavior
    if "use_ssl" in params:
        kwargs["use_ssl"] = False
    if "use_tls" in params:
        kwargs["use_tls"] = True
    if "disable_starttls" in params:
        kwargs["disable_starttls"] = False

    # Supply ssl_context if supported (this is used during STARTTLS)
    if "ssl_context" in params:
        kwargs["ssl_context"] = xmpp.ssl_context

    # Address routing: different builds accept different shapes.
    if "address" in params:
        # Some builds want address=(host,port)
        kwargs["address"] = (ip, port)
        return (), kwargs

    # Some builds want host/port kwargs
    if "host" in params or "port" in params:
        if "host" in params:
            kwargs["host"] = ip
        if "port" in params:
            kwargs["port"] = port
        return (), kwargs

    # Fallback: positional (ip, port) or ((ip,port),)
    # Prefer ((ip,port),) because that's common in XMPP libs.
    try:
        # If first param looks like "address" positional
        first = next(iter(params.values()))
        if first.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            return ((ip, port),), kwargs
    except StopIteration:
        pass

    return (ip, port), kwargs


async def amain() -> int:
    cfg = load_cfg()
    ip = resolve_ipv4(cfg.host)

    logging.info(
        "connecting jid=%s host=%s(%s) port=%d room=%s insecure_tls=%s",
        f"agent-tests@{cfg.domain}",
        cfg.host,
        ip,
        cfg.port,
        cfg.room,
        cfg.insecure_tls,
    )

    xmpp = AgentBot(cfg)

    args, kwargs = build_connect_call(xmpp, ip, cfg.port)
    res = xmpp.connect(*args, **kwargs)
    ok = await maybe_await(res)

    # Some slixmpp builds return None on success
    if ok is None:
        logging.debug("connect() returned None; treating as success")
        ok = True

    if not ok:
        raise RuntimeError("connect() returned False")

    # If your build has .process(), fine. If not, run by waiting on events.
    if hasattr(xmpp, "process"):
        logging.info("running via xmpp.process()")
        # Run until we send hello, then disconnect handler stops it.
        # forever=False is safer when we want to exit.
        xmpp.process(forever=False)
        return 0

    # Async-native: wait for hello then for disconnect.
    logging.info("running async-native (no .process() on this slixmpp build)")
    await asyncio.wait_for(xmpp._hello_sent.wait(), timeout=20.0)
    # Give it a moment to actually close
    await asyncio.sleep(0.5)
    return 0


def main() -> int:
    logging.basicConfig(
        level=os.getenv("AUTOMATR_XMPP_LOGLEVEL", "DEBUG").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())

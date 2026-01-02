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

import bot_commands


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None:
        raise SystemExit(f"Missing required env var: {name}")
    return v


def derive_node_name() -> str:
    # DB/UI-provided name injected by host (app.py sets AUTOMATR_NODE)
    node = (os.getenv("AUTOMATR_NODE") or os.getenv("AUTOMATR_CONTAINER_NAME") or "").strip()
    if node:
        return node

    # fallback
    hn = (os.getenv("HOSTNAME") or socket.gethostname() or "agent").strip()
    if hn.startswith("automatr-"):
        hn = hn[len("automatr-") :]
    return hn


def derive_nick(node: str) -> str:
    return f"agent-{node}"


@dataclass
class Cfg:
    domain: str
    host: str
    port: int
    password: str
    room: str
    node: str
    nick: str
    insecure_tls: bool


def load_cfg() -> Cfg:
    domain = env("AUTOMATR_XMPP_DOMAIN", "automatr-xmpp.local")
    host = env("AUTOMATR_XMPP_HOST", "automatr-prosody")
    port = int(env("AUTOMATR_XMPP_PORT", "5222"))
    password = env("AUTOMATR_XMPP_PASSWORD", "supersecret")
    room = env("AUTOMATR_XMPP_MUC", f"automatr@conference.{domain}")
    insecure_tls = env("AUTOMATR_XMPP_INSECURE_TLS", "0").lower() in ("1", "true", "yes", "on")
    node = derive_node_name()
    nick = derive_nick(node)
    return Cfg(domain=domain, host=host, port=port, password=password, room=room, node=node, nick=nick, insecure_tls=insecure_tls)


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
        self._ready = asyncio.Event()
        self._recent = {}

        # XML-first on 5222; STARTTLS allowed
        self.use_ssl = False
        self.use_tls = True
        self.disable_starttls = False
        self.ssl_context = make_ssl_context(cfg.insecure_tls)

        self.register_plugin("xep_0030")  # disco
        self.register_plugin("xep_0199")  # ping
        self.register_plugin("xep_0045")  # muc

        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("connection_failed", self.on_connection_failed)
        self.add_event_handler("disconnected", self.on_disconnected)

        # slixmpp 1.10: be explicit
        self.add_event_handler("message", self.on_message)
        self.add_event_handler("groupchat_message", self.on_message)
        self.add_event_handler("chat_message", self.on_message)

    async def on_session_start(self, _event):
        logging.info("session_start: join %s as %s (node=%s)", self.cfg.room, self.cfg.nick, self.cfg.node)
        self.send_presence()
        try:
            await self.get_roster()
        except Exception:
            logging.debug("get_roster failed (ignored)", exc_info=True)

        self.plugin["xep_0045"].join_muc(self.cfg.room, self.cfg.nick)

        await asyncio.sleep(0.75)
        self.send_message(mto=self.cfg.room, mbody=f"hello from {self.cfg.nick}", mtype="groupchat")
        self._ready.set()

    def on_connection_failed(self, _event):
        logging.error("connection_failed")

    def on_disconnected(self, _event):
        logging.warning("disconnected")

    def on_message(self, msg):
        body = (msg.get("body") or "").strip()
        if not body:
            return

        mtype = (msg.get("type") or "").strip()
        frm = str(msg.get("from") or "").strip()

        now = asyncio.get_running_loop().time()
        key = (mtype, frm, body)

        # purge old
        for k, ts in list(self._recent.items()):
            if now - ts > 2.0:
                del self._recent[k]

        if key in self._recent:
            return
        self._recent[key] = now

        # Debug: comment out later if noisy
        logging.info("rx type=%s from=%s body=%r", mtype, frm, body)

        is_group = (mtype == "groupchat")
        is_direct = (mtype == "chat")

        # Ignore our own MUC echoes: room@.../nick
        if is_group and frm.endswith("/" + self.cfg.nick):
            return

        ctx = bot_commands.BotContext(
            node=self.cfg.node,
            nick=self.cfg.nick,
            room=self.cfg.room,
            jid=str(self.boundjid),
        )

        # Canonical entry point (bot_commands also provides compat aliases)
        response = bot_commands.handle_message(body, ctx, is_direct=is_direct, is_group=is_group)
        if response is None:
            return

        if is_group:
            self.send_message(mto=self.cfg.room, mbody=response, mtype="groupchat")
        else:
            self.send_message(mto=frm, mbody=response, mtype="chat")


async def maybe_await(x: Any) -> Any:
    if inspect.isawaitable(x):
        return await x
    return x


def build_connect_call(xmpp: AgentBot, ip: str, port: int) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    sig = inspect.signature(xmpp.connect)
    params = sig.parameters
    logging.info("slixmpp.connect signature: %s", sig)

    kwargs: Dict[str, Any] = {}
    if "use_ssl" in params:
        kwargs["use_ssl"] = False
    if "use_tls" in params:
        kwargs["use_tls"] = True
    if "disable_starttls" in params:
        kwargs["disable_starttls"] = False
    if "ssl_context" in params:
        kwargs["ssl_context"] = xmpp.ssl_context

    if "address" in params:
        kwargs["address"] = (ip, port)
        return (), kwargs

    if "host" in params or "port" in params:
        if "host" in params:
            kwargs["host"] = ip
        if "port" in params:
            kwargs["port"] = port
        return (), kwargs

    return ((ip, port),), kwargs


async def amain() -> int:
    cfg = load_cfg()
    ip = resolve_ipv4(cfg.host)

    logging.info(
        "connecting jid=%s host=%s(%s) port=%d room=%s node=%s nick=%s insecure_tls=%s",
        f"agent-tests@{cfg.domain}",
        cfg.host,
        ip,
        cfg.port,
        cfg.room,
        cfg.node,
        cfg.nick,
        cfg.insecure_tls,
    )

    xmpp = AgentBot(cfg)

    args, kwargs = build_connect_call(xmpp, ip, cfg.port)
    res = xmpp.connect(*args, **kwargs)
    ok = await maybe_await(res)

    if ok is None:
        ok = True
    if not ok:
        raise RuntimeError("connect() returned False")

    # For older non-async slixmpp, process exists; for 1.10 async-native it usually doesn't.
    if hasattr(xmpp, "process"):
        xmpp.process(forever=True)
        return 0

    await xmpp._ready.wait()
    while True:
        await asyncio.sleep(3600)


def main() -> int:
    logging.basicConfig(
        level=os.getenv("AUTOMATR_XMPP_LOGLEVEL", "DEBUG").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())

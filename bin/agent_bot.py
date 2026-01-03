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
    node = (os.getenv("AUTOMATR_NODE") or os.getenv("AUTOMATR_CONTAINER_NAME") or "").strip()
    if node:
        return node

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

    return Cfg(
        domain=domain,
        host=host,
        port=port,
        password=password,
        room=room,
        node=node,
        nick=nick,
        insecure_tls=insecure_tls,
    )


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
        jid = f"{cfg.nick}@{cfg.domain}"
        super().__init__(jid, cfg.password)

        self.cfg = cfg
        self._ready = asyncio.Event()
        self._recent: dict[tuple[str, str, str], float] = {}

        # Prevent infinite register loops on bad creds / server behavior
        self._register_attempted = False
        self._reconnect_after_register = False

        # XML-first on 5222; STARTTLS allowed
        self.use_ssl = False
        self.use_tls = True
        self.disable_starttls = False
        self.ssl_context = make_ssl_context(cfg.insecure_tls)

        # Core plugins
        self.register_plugin("xep_0030")  # disco
        self.register_plugin("xep_0199")  # ping
        self.register_plugin("xep_0045")  # muc

        # In-band registration (XEP-0077)
        self.register_plugin("xep_0077")
        self.add_event_handler("register", self.on_register)

        # Lifecycle
        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("connection_failed", self.on_connection_failed)
        self.add_event_handler("disconnected", self.on_disconnected)
        self.add_event_handler("failed_auth", self.on_failed_auth)

        # Messages
        self.add_event_handler("message", self.on_message)
        self.add_event_handler("groupchat_message", self.on_message)
        self.add_event_handler("chat_message", self.on_message)

    async def on_failed_auth(self, _event):
        # This fires when auth fails and no successful method is found.
        # If the server supports in-band registration, slixmpp will ALSO trigger "register".
        logging.warning("auth failed for %s (user=%s). may attempt in-band registration if available.",
                        self.boundjid.bare, self.boundjid.user)

    async def on_register(self, _iq):
        """
        Triggered when server advertises in-band registration and the current JID is not authorized.
        We attempt to create the account ONCE per boot.
        If it succeeds, we disconnect and reconnect (clean auth path).
        """
        if self._register_attempted:
            logging.error("in-band registration already attempted once; refusing to loop for %s", self.boundjid.bare)
            self.disconnect()
            return

        self._register_attempted = True

        logging.warning("in-band registration: attempting for %s", self.boundjid.bare)
        try:
            iq = self.Iq()
            iq["type"] = "set"
            iq["register"]["username"] = self.boundjid.user
            iq["register"]["password"] = self.cfg.password

            # Some servers require a data form; Prosody accepts username/password.
            await iq.send()

            logging.warning("in-band registration: success for %s", self.boundjid.bare)

            # We want a clean SASL auth after creation.
            # Disconnect now; the outer runner will reconnect by restarting, or we can reconnect here.
            self._reconnect_after_register = True
            self.disconnect()

        except Exception as e:
            # If the account already exists, some servers respond with conflict (409) or similar.
            # Slixmpp surfaces various exception shapes; log and stop to avoid spam.
            logging.exception("in-band registration: failed for %s (%s)", self.boundjid.bare, e)
            self.disconnect()

    async def on_session_start(self, _event):
        logging.info(
            "session_start: jid=%s join %s as %s (node=%s)",
            self.boundjid.bare,
            self.cfg.room,
            self.cfg.nick,
            self.cfg.node,
        )
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
        logging.error("connection_failed jid=%s", self.boundjid.bare)

    def on_disconnected(self, _event):
        logging.warning("disconnected jid=%s", self.boundjid.bare)

    def on_message(self, msg):
        body = (msg.get("body") or "").strip()
        if not body:
            return

        mtype = (msg.get("type") or "").strip()
        frm = str(msg.get("from") or "").strip()

        now = asyncio.get_running_loop().time()
        key = (mtype, frm, body)

        for k, ts in list(self._recent.items()):
            if now - ts > 2.0:
                del self._recent[k]

        if key in self._recent:
            return
        self._recent[key] = now

        is_group = (mtype == "groupchat")
        is_direct = (mtype == "chat")

        if is_group and frm.endswith("/" + self.cfg.nick):
            return

        ctx = bot_commands.BotContext(
            node=self.cfg.node,
            nick=self.cfg.nick,
            room=self.cfg.room,
            jid=str(self.boundjid),
        )

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


async def run_bot_once(cfg: Cfg) -> int:
    ip = resolve_ipv4(cfg.host)
    jid = f"{cfg.nick}@{cfg.domain}"

    logging.info(
        "connecting jid=%s host=%s(%s) port=%d room=%s node=%s nick=%s insecure_tls=%s",
        jid,
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

    # Some builds are blocking, some async-native
    if hasattr(xmpp, "process"):
        xmpp.process(forever=False)  # return when disconnected
    else:
        # Wait until we either got ready or disconnected

        ready_task = asyncio.create_task(xmpp._ready.wait())
        try:
            await asyncio.wait({ready_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            if not ready_task.done():
                ready_task.cancel()

        # If we registered successfully, reconnect once to authenticate cleanly
    if getattr(xmpp, "_reconnect_after_register", False):
        logging.warning("reconnecting after successful registration for %s", xmpp.boundjid.bare)
        await asyncio.sleep(0.5)
        return 2  # signal caller to reconnect

    return 0


async def amain() -> int:
    cfg = load_cfg()

    # Run forever (connect, register if needed, reconnect once, then stay connected)
    while True:
        code = await run_bot_once(cfg)

        # code==2 means we registered and want to reconnect immediately
        if code == 2:
            continue

        # If we ever disconnect unexpectedly, wait a bit and reconnect
        if code != 0:
            await asyncio.sleep(2.0)
            continue

        # Normal connected path: keep process alive
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

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
from slixmpp.exceptions import IqError, IqTimeout

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
    # XMPP served domain (Prosody VirtualHost)
    domain: str
    # network host to connect to (docker service name or LAN host)
    host: str
    # XMPP c2s port (5222)
    port: int
    password: str
    # full MUC JID (e.g. automatr@conference.xps.local)
    room: str
    node: str
    nick: str
    insecure_tls: bool
    # STARTTLS policy
    starttls_required: bool


def load_cfg() -> Cfg:
    # Domain MUST match Prosody VirtualHost.
    domain = (os.getenv("AUTOMATR_XMPP_DOMAIN") or "xps.local").strip()

    # Host is the TCP host to connect to (container DNS name or LAN hostname).
    host = (os.getenv("AUTOMATR_XMPP_HOST") or "automatr-prosody").strip()

    # c2s (XMPP client) port. DO NOT use 5280/5281 (those are HTTP/BOSH/WS).
    port_s = (os.getenv("AUTOMATR_XMPP_C2S_PORT") or os.getenv("AUTOMATR_XMPP_PORT") or "5222").strip()
    try:
        port = int(port_s)
    except ValueError:
        port = 5222
    if port in (5280, 5281, 80, 443):
        logging.warning("AUTOMATR_XMPP_PORT=%s looks like HTTP; forcing 5222 for XMPP c2s", port)
        port = 5222

    password = (os.getenv("AUTOMATR_XMPP_PASSWORD") or "supersecret").strip()
    muc = (os.getenv("AUTOMATR_XMPP_MUC") or f"automatr@conference.{domain}").strip()

    insecure_tls = (os.getenv("AUTOMATR_XMPP_INSECURE_TLS") or "0").lower() in ("1", "true", "yes", "on")
    starttls_required = (os.getenv("AUTOMATR_XMPP_STARTTLS_REQUIRED") or "1").lower() in ("1", "true", "yes", "on")

    node = derive_node_name()
    nick = derive_nick(node)

    return Cfg(
        domain=domain,
        host=host,
        port=port,
        password=password,
        room=muc,
        node=node,
        nick=nick,
        insecure_tls=insecure_tls,
        starttls_required=starttls_required,
    )


def resolve_ipv4(name: str) -> str:
    return socket.gethostbyname(name)


def make_ssl_context(insecure: bool) -> ssl.SSLContext:
    """
    Used for STARTTLS validation.
    - secure: normal system trust store + hostname verification.
    - insecure: accept self-signed (dev).
    """
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def maybe_await(x: Any) -> Any:
    if inspect.isawaitable(x):
        return await x
    return x


class AgentBot(slixmpp.ClientXMPP):
    """
    Correct protocol choices for Prosody c2s:
    - TCP to 5222
    - STARTTLS upgrade (not direct TLS-on-connect)
    - optional in-band registration (XEP-0077) if account doesn't exist
    - join MUC (XEP-0045) and wait for join confirmation
    """

    def __init__(self, cfg: Cfg):
        jid = f"{cfg.nick}@{cfg.domain}"
        super().__init__(jid, cfg.password)

        self.cfg = cfg

        self._ready = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._recent: dict[tuple[str, str, str], float] = {}

        self._register_attempted = False
        self._reconnect_after_register = False

        # ---- PROTOCOL: STARTTLS, not direct TLS ----
        # In slixmpp:
        # - use_ssl=True  => legacy "old-style" direct TLS on connect (NOT what we want for 5222)
        # - use_tls=True  => STARTTLS (upgrade) when server offers it (what we want)
        self.use_ssl = False
        self.use_tls = True
        self.disable_starttls = False

        # If you *require* STARTTLS (recommended), keep this True.
        # If you need to debug plaintext on LAN (not recommended), set env to 0.
        self.require_starttls = bool(cfg.starttls_required)

        # SSL validation policy for the STARTTLS upgrade.
        self.ssl_context = make_ssl_context(cfg.insecure_tls)

        # Auto-register when auth fails / account missing (Prosody must allow XEP-0077).
        # Slixmpp triggers the "register" event when auto_register is True and auth fails.
        self.auto_register = True

        # Plugins
        self.register_plugin("xep_0030")  # disco
        self.register_plugin("xep_0199")  # ping
        self.register_plugin("xep_0045")  # muc
        self.register_plugin("xep_0077")  # in-band registration

        # Events
        self.add_event_handler("register", self.on_register)
        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("failed_auth", self.on_failed_auth)
        self.add_event_handler("connection_failed", self.on_connection_failed)
        self.add_event_handler("disconnected", self.on_disconnected)

        # Messages
        self.add_event_handler("message", self.on_message)
        self.add_event_handler("groupchat_message", self.on_message)
        self.add_event_handler("chat_message", self.on_message)

    async def on_failed_auth(self, _event):
        logging.warning("auth failed for %s", self.boundjid.bare)

    async def on_register(self, _iq):
        """
        Attempt XEP-0077 in-band registration exactly once.
        If the account already exists (conflict), we reconnect and login normally.
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
            await iq.send()

            logging.warning("in-band registration: success for %s", self.boundjid.bare)
            self._reconnect_after_register = True
            self.disconnect()
        except (IqError, IqTimeout) as e:
            # Prosody typically returns <conflict/> if user exists
            cond = None
            try:
                cond = e.iq["error"]["condition"]  # type: ignore[attr-defined]
            except Exception:
                pass

            msg = str(e).lower()
            if cond == "conflict" or "conflict" in msg or "409" in msg:
                logging.warning("in-band registration: already exists for %s; will login", self.boundjid.bare)
                self._reconnect_after_register = True
                self.disconnect()
            else:
                logging.exception("in-band registration: failed for %s (%s)", self.boundjid.bare, e)
                self.disconnect()
        except Exception as e:
            logging.exception("in-band registration: failed for %s (%s)", self.boundjid.bare, e)
            self.disconnect()

    async def on_session_start(self, _event):
        logging.info(
            "session_start jid=%s connect_host=%s:%d join=%s nick=%s node=%s",
            self.boundjid.bare,
            self.cfg.host,
            self.cfg.port,
            self.cfg.room,
            self.cfg.nick,
            self.cfg.node,
        )

        self.send_presence()
        try:
            await self.get_roster()
        except Exception:
            pass

        # IMPORTANT: wait for join confirmation so bots reliably appear online
        try:
            join = getattr(self.plugin["xep_0045"], "join_muc_wait", None)
            if callable(join):
                await join(self.cfg.room, self.cfg.nick)
            else:
                # older slixmpp: best-effort join
                self.plugin["xep_0045"].join_muc(self.cfg.room, self.cfg.nick)
                await asyncio.sleep(0.5)
        except Exception:
            logging.exception("MUC join failed")
            self.disconnect()
            return

        self.send_message(mto=self.cfg.room, mbody=f"hello from {self.cfg.nick}", mtype="groupchat")
        self._ready.set()

    def on_connection_failed(self, _event):
        logging.error("connection_failed")
        self._disconnected.set()

    def on_disconnected(self, _event):
        logging.warning("disconnected")
        self._disconnected.set()

    def on_message(self, msg):
        body = (msg.get("body") or "").strip()
        if not body:
            return

        mtype = (msg.get("type") or "").strip()
        frm = str(msg.get("from") or "").strip()

        # de-dupe bursts
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

        # Ignore our own group echoes
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


def build_connect_call(xmpp: AgentBot, host: str, port: int) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    """
    Slixmpp connect signature varies by version. Prefer (address=(host,port), ...)
    but support older variants.
    """
    sig = inspect.signature(xmpp.connect)
    params = sig.parameters
    logging.info("slixmpp.connect signature: %s", sig)

    kwargs: Dict[str, Any] = {}

    # Most versions accept `address`
    if "address" in params:
        kwargs["address"] = (host, port)

    # Some versions accept host/port separately
    if "host" in params:
        kwargs["host"] = host
    if "port" in params:
        kwargs["port"] = port

    # Some versions accept `use_ssl` / `use_tls` in connect()
    if "use_ssl" in params:
        kwargs["use_ssl"] = False
    if "use_tls" in params:
        kwargs["use_tls"] = True
    if "disable_starttls" in params:
        kwargs["disable_starttls"] = False

    # Many versions accept ssl_context for STARTTLS validation
    if "ssl_context" in params:
        kwargs["ssl_context"] = xmpp.ssl_context

    if kwargs:
        return (), kwargs

    # Fallback: positional address tuple
    return ((host, port),), {}


async def run_bot_once(cfg: Cfg) -> int:
    ip = resolve_ipv4(cfg.host)
    jid = f"{cfg.nick}@{cfg.domain}"

    logging.info(
        "connecting jid=%s host=%s(%s) port=%d room=%s starttls_required=%s insecure_tls=%s",
        jid,
        cfg.host,
        ip,
        cfg.port,
        cfg.room,
        cfg.starttls_required,
        cfg.insecure_tls,
    )

    xmpp = AgentBot(cfg)

    args, kwargs = build_connect_call(xmpp, cfg.host, cfg.port)

    res = xmpp.connect(*args, **kwargs)
    ok = await maybe_await(res)

    # Some slixmpp versions return None on success
    if ok is None:
        ok = True
    if not ok:
        raise RuntimeError("connect() returned False")

    # Run XMPP engine in background (asyncio)
    process_fn = getattr(xmpp, "process", None)
    if callable(process_fn):
        # In slixmpp, process() is non-blocking under asyncio and schedules tasks;
        # but some builds still want you to call it.
        try:
            process_fn(forever=False)
        except TypeError:
            process_fn()

    # Wait for either ready or disconnect
    ready_task = asyncio.create_task(xmpp._ready.wait())
    disc_task = asyncio.create_task(xmpp._disconnected.wait())
    done, pending = await asyncio.wait({ready_task, disc_task}, return_when=asyncio.FIRST_COMPLETED)

    for t in pending:
        t.cancel()

    # If we registered, reconnect and then authenticate normally
    if xmpp._reconnect_after_register:
        logging.warning("reconnecting after registration")
        await asyncio.sleep(0.5)
        return 2

    # Disconnected before ready
    if disc_task in done and xmpp._disconnected.is_set() and not xmpp._ready.is_set():
        return 1

    return 0


async def amain() -> int:
    cfg = load_cfg()

    while True:
        try:
            code = await run_bot_once(cfg)
        except Exception:
            logging.exception("run_bot_once failed; retrying")
            await asyncio.sleep(2.0)
            continue

        if code == 2:
            continue

        # Stay alive; slixmpp runs on the loop.
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

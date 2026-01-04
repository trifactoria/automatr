#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import os
import ssl
import sys
import time
from collections import deque
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
    """
    agent_jid = (os.getenv("AUTOMATR_AGENT_JID") or "").strip()
    if agent_jid:
        localpart = agent_jid.split("@", 1)[0]
        nick = localpart
        return agent_jid, localpart, nick

    agent_name = (os.getenv("AUTOMATR_AGENT_NAME") or "").strip()
    if agent_name:
        jid = f"{agent_name}@{domain}"
        nick = agent_name
        return jid, agent_name, nick

    container_name = (os.getenv("AUTOMATR_CONTAINER_NAME") or "").strip()
    node = (os.getenv("AUTOMATR_NODE") or "").strip()

    base = container_name or node or "something-broke"
    agent_name = f"agent-{base}"
    jid = f"{agent_name}@{domain}"
    nick = agent_name
    return jid, agent_name, nick


def _derive_node_value(cfg_username: str) -> str:
    container_name = (os.getenv("AUTOMATR_CONTAINER_NAME") or "").strip()
    node = (os.getenv("AUTOMATR_NODE") or "").strip()
    return container_name or node or cfg_username


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
    jid: str
    username: str
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
# Commands integration
# ----------------------------

from bot_commands import BotContext, handle_message  # noqa: E402


# ----------------------------
# XMPP Bot (slixmpp)
# ----------------------------

import slixmpp  # noqa: E402
from slixmpp import ClientXMPP  # noqa: E402


class AgentBot(ClientXMPP):
    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        super().__init__(cfg.jid, cfg.password)

        self.ssl_context = make_ssl_context(cfg.insecure_tls)

        self._ready = asyncio.Event()
        self._disconnected = asyncio.Event()

        # registration + retry control
        self._register_enabled = cfg.register
        self._attempt_register_next = False   # set if auth fails and we want to register
        self._register_in_progress = False
        self._reconnect_after_register = False

        # Plugins
        self.register_plugin("xep_0030")  # disco
        self.register_plugin("xep_0199")  # ping
        self.register_plugin("xep_0045")  # MUC
        self.register_plugin("xep_0077")  # in-band registration

        # If we’re registering, force XEP-0077 flow (server must advertise/register enabled)
        self["xep_0077"].force_registration = False

        # Events
        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("disconnected", self.on_disconnected)
        self.add_event_handler("connection_failed", self.on_connection_failed)

        # Fires when XEP-0077 registration flow is active
        self.add_event_handler("register", self.on_register)

        # Fires on auth failures
        self.add_event_handler("failed_auth", self.on_failed_auth)

        # Messages
        self.add_event_handler("groupchat_message", self.on_groupchat_message)
        self.add_event_handler("message", self.on_message)

        self.client_name = "automatr-agent"

        self._ctx_node = _derive_node_value(cfg.username)

        # inbound dedupe (stops repeated handler firings)
        self._seen: dict[str, float] = {}
        self._seen_order: deque[tuple[float, str]] = deque()
        self._seen_ttl_s = float(os.getenv("AUTOMATR_XMPP_DEDUPE_TTL", "2.0"))
        self._seen_max = int(os.getenv("AUTOMATR_XMPP_DEDUPE_MAX", "512"))

    def _mk_ctx(self) -> BotContext:
        return BotContext(
            node=self._ctx_node,
            nick=self.cfg.nick,
            room=self.cfg.muc,
            jid=self.cfg.jid,
        )

    def _safe_body(self, msg) -> str:
        return (msg.get("body") or "").strip()

    def _is_from_self(self, msg) -> bool:
        try:
            frm = msg.get("from")
            if not frm:
                return False
            if getattr(frm, "bare", None) and frm.bare == self.boundjid.bare:
                return True
            res = getattr(frm, "resource", None)
            if res and res == self.cfg.nick:
                return True
            return False
        except Exception:
            return False

    def _msg_key(self, msg) -> str:
        mtype = (msg.get("type") or "").lower()
        frm = str(msg.get("from") or "")
        mid = str(msg.get("id") or "")
        body = (msg.get("body") or "").strip()
        raw = f"{mtype}\n{frm}\n{mid}\n{body}"
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()

    def _dedupe_drop(self, msg) -> bool:
        now = time.monotonic()
        key = self._msg_key(msg)

        cutoff = now - self._seen_ttl_s
        while self._seen_order and self._seen_order[0][0] < cutoff:
            ts, k = self._seen_order.popleft()
            if self._seen.get(k) == ts:
                self._seen.pop(k, None)

        while len(self._seen_order) > self._seen_max:
            ts, k = self._seen_order.popleft()
            if self._seen.get(k) == ts:
                self._seen.pop(k, None)

        if key in self._seen:
            return True
        self._seen[key] = now
        self._seen_order.append((now, key))
        return False

    # ---- auth/register flow ----

    async def on_failed_auth(self, _event):
        # This is the key: if user doesn't exist yet, attempt in-band registration on next connect.
        logging.warning("failed_auth for jid=%s (register=%s)", self.cfg.jid, self._register_enabled)

        if self._register_enabled and not self._register_in_progress:
            logging.warning("will retry with in-band registration enabled")
            self._attempt_register_next = True

        self._disconnected.set()
        self.disconnect()

    async def on_register(self, _event):
        # Only do this if we explicitly decided to register on this connection attempt.
        if not self._register_enabled or not self._attempt_register_next:
            logging.warning("register event fired but registration not requested; ignoring")
            return

        self._register_in_progress = True
        try:
            logging.warning("attempting in-band registration: %s", self.cfg.jid)
            await self["xep_0077"].register(self.cfg.username, self.cfg.password)
            logging.warning("registration succeeded; reconnecting to login normally")
            self._reconnect_after_register = True
            self.disconnect()
        except Exception as e:
            msg = str(e).lower()
            if "conflict" in msg or "already" in msg or "exists" in msg:
                logging.warning("registration: already exists; proceed to login")
                self._attempt_register_next = False
                self._register_in_progress = False
                return
            logging.exception("registration failed (server may not allow it).")
            self._attempt_register_next = False
            self._register_in_progress = False

    async def on_session_start(self, _event):
        try:
            logging.info("session_start jid=%s", self.boundjid.bare)

            self.send_presence()
            try:
                await self.get_roster()
            except Exception:
                pass

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

    # ---- message handling ----

    async def on_groupchat_message(self, msg):
        try:
            if self._is_from_self(msg) or self._dedupe_drop(msg):
                return

            body = self._safe_body(msg)
            if not body:
                return

            sender_nick = ""
            try:
                sender_nick = getattr(msg.get("from"), "resource", "") or ""
            except Exception:
                sender_nick = ""

            ctx = self._mk_ctx()
            resp = handle_message(body, ctx, is_direct=False, is_group=True)
            if not resp:
                return

            out = f"{sender_nick}: {resp}" if sender_nick else resp
            self.send_message(mto=self.cfg.muc, mbody=out, mtype="groupchat")
        except Exception:
            logging.exception("error handling groupchat_message")

    async def on_message(self, msg):
        try:
            mtype = (msg.get("type") or "").lower()
            if mtype not in ("chat", "normal"):
                return

            if self._is_from_self(msg) or self._dedupe_drop(msg):
                return

            body = self._safe_body(msg)
            if not body:
                return

            ctx = self._mk_ctx()
            resp = handle_message(body, ctx, is_direct=True, is_group=False)
            if not resp:
                return

            to_jid = msg["from"].bare if msg.get("from") else None
            if not to_jid:
                return

            self.send_message(mto=to_jid, mbody=resp, mtype="chat")
        except Exception:
            logging.exception("error handling direct message")


async def run_once(cfg: Cfg) -> int:
    """
    Return codes:
      0 = connected + joined room
      1 = failed before ready
      2 = registration succeeded; retry login
      3 = auth failed; retry (maybe with registration)
    """
    xmpp = AgentBot(cfg)

    # If previous attempt decided to register, we need to force XEP-0077 on connect.
    # (We set this before connect so the feature negotiation can trigger register event.)
    if cfg.register:
        # Start in normal mode; bot flips to register-mode only after failed_auth.
        pass

    connect_sig = inspect.signature(xmpp.connect)
    logging.info(
        "connecting jid=%s host=%s port=%d room=%s insecure_tls=%s register=%s (connect sig=%s)",
        xmpp.boundjid.bare, cfg.host, cfg.port, cfg.muc, cfg.insecure_tls, cfg.register, connect_sig
    )

    # connect
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

    # If we hit failed_auth, bot disconnected itself.
    if xmpp._attempt_register_next and cfg.register:
        # next run should force registration
        return 3

    return 1


async def amain() -> int:
    cfg = load_cfg()

    logging.info("resolved identity: jid=%s username=%s nick=%s domain=%s",
                 cfg.jid, cfg.username, cfg.nick, cfg.domain)

    backoff = 1.0
    want_register_mode = False

    while True:
        try:
            # When we decide to register, we flip force_registration for that connection.
            if cfg.register and want_register_mode:
                # re-init per run_once, so we encode this decision via env-like global:
                # easiest is to stash in env for this run.
                os.environ["AUTOMATR_FORCE_REGISTER_ON_CONNECT"] = "1"
            else:
                os.environ.pop("AUTOMATR_FORCE_REGISTER_ON_CONNECT", None)

            # Build bot and connect
            xmpp = AgentBot(cfg)

            # Apply force registration if requested
            if cfg.register and want_register_mode:
                xmpp["xep_0077"].force_registration = True
                xmpp._attempt_register_next = True
                logging.warning("FORCING in-band registration on this connection attempt")

            fut = xmpp.connect(host=cfg.host, port=cfg.port)
            ok = await fut
            if not ok:
                rc = 1
            else:
                ready_task = asyncio.create_task(xmpp._ready.wait())
                disc_task = asyncio.create_task(xmpp._disconnected.wait())
                done, pending = await asyncio.wait({ready_task, disc_task}, return_when=asyncio.FIRST_COMPLETED)
                for t in pending:
                    t.cancel()

                if xmpp._reconnect_after_register:
                    rc = 2
                elif xmpp._ready.is_set():
                    rc = 0
                else:
                    # failed_auth sets _attempt_register_next if register is enabled
                    rc = 3 if (cfg.register and xmpp._attempt_register_next) else 1

        except Exception:
            logging.exception("bot crashed; restarting")
            rc = 1

        if rc == 0:
            logging.info("bot is ready (joined room). staying alive.")
            want_register_mode = False
            backoff = 1.0
            await asyncio.sleep(3600)
            continue

        if rc == 2:
            # registration succeeded; next connect should be normal auth
            logging.warning("registration completed; retrying normal login")
            want_register_mode = False
            await asyncio.sleep(0.5)
            continue

        if rc == 3:
            # auth failed and register is enabled; next connect should force register
            logging.warning("auth failed; next attempt will force in-band registration")
            want_register_mode = True
            await asyncio.sleep(0.5)
            continue

        logging.warning("bot not ready; sleeping %.1fs then retry", backoff)
        await asyncio.sleep(backoff)
        backoff = min(8.0, backoff * 1.6)


def main() -> int:
    logging.basicConfig(
        level=os.getenv("AUTOMATR_XMPP_LOGLEVEL", "DEBUG").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.info("slixmpp %s", getattr(slixmpp, "__version__", "unknown"))
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())

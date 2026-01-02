"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import XMPP_CONFIG from "@/lib/xmppConfig";

type Msg = { id: string; from: string; body: string; time: string };

// Dynamically load headless (client-only)
let headlessPromise: Promise<any> | null = null;
async function loadHeadless() {
  if (!headlessPromise) {
    headlessPromise = import("@converse/headless").then((m) => m.default ?? m);
  }
  return headlessPromise;
}

// Internal handle captured via plugin
let _converseRef: any = null;
let pluginInstalled = false;
let initialized = false;

async function ensurePluginInstalled(converse: any) {
  if (pluginInstalled) return;

  // Plugin must be registered BEFORE initialize
  converse.plugins.add("automatr-bridge", {
    initialize() {
      // In Converse plugin context, `this._converse` is the internal instance
      _converseRef = (this as any)._converse;
    },
  });

  pluginInstalled = true;
}

async function ensureInitialized(opts: { jid: string; password: string }) {
  const converse = await loadHeadless();
  await ensurePluginInstalled(converse);

  if (!initialized) {
    initialized = true;

    converse.initialize({
      authentication: "login",
      auto_login: true,
      jid: opts.jid,
      password: opts.password,

      websocket_url: XMPP_CONFIG.useWebSocket ? XMPP_CONFIG.websocketUrl : undefined,
      bosh_service_url: XMPP_CONFIG.useWebSocket ? undefined : XMPP_CONFIG.boshUrl,

      // CRITICAL: whitelist the plugin or it won't run
      whitelisted_plugins: ["automatr-bridge"],

      // Headless mode
      view_mode: "headless",
      loglevel: "warn",
    });
  }

  // Wait for plugin to run and provide _converse
  const start = Date.now();
  while (!_converseRef) {
    if (Date.now() - start > 5000) {
      throw new Error("Headless bridge plugin did not initialize (_converse missing)");
    }
    await new Promise((r) => setTimeout(r, 50));
  }

  // Wait until Converse is ready to use (if available)
  if (_converseRef.api?.waitUntil) {
    await _converseRef.api.waitUntil("statusInitialized");
  }
}

export function ChatModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [jid, setJid] = useState("");
  const [password, setPassword] = useState("");

  const [roomJid, setRoomJid] = useState(
    XMPP_CONFIG.defaultRoom && XMPP_CONFIG.mucDomain
      ? `${XMPP_CONFIG.defaultRoom}@${XMPP_CONFIG.mucDomain}`
      : ""
  );

  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const transportLabel = useMemo(
    () => (XMPP_CONFIG.useWebSocket ? "WebSocket" : "BOSH"),
    []
  );

  useEffect(() => {
    setJid(localStorage.getItem("automatr_xmpp_jid") || "");
    setPassword(localStorage.getItem("automatr_xmpp_pw") || "");
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  useEffect(() => {
    if (!open) {
      setError(null);
      setConnecting(false);
    }
  }, [open]);

  async function connect() {
    try {
      setError(null);
      setConnecting(true);
      setConnected(false);
      setMessages([]);

      const j = jid.trim();
      if (!j) throw new Error(`Enter a JID (e.g. andy@${XMPP_CONFIG.domain})`);
      if (!password) throw new Error("Enter a password");
      if (!roomJid) throw new Error("Room JID is missing");

      localStorage.setItem("automatr_xmpp_jid", j);
      localStorage.setItem("automatr_xmpp_pw", password);

      await ensureInitialized({ jid: j, password });

      // Install message listener once
      if (!_converseRef.__automatrListenersInstalled) {
        _converseRef.__automatrListenersInstalled = true;

        _converseRef.api.listen.on("message", (msg: any) => {
          const body = msg?.get?.("body");
          if (!body) return;

          const from = msg?.get?.("from") || "unknown";
          const time = new Date().toLocaleTimeString();

          setMessages((prev) => [
            ...prev,
            { id: `${Date.now()}-${Math.random()}`, from, body, time },
          ]);
        });
      }

      // Join room
      const nick = j.split("@")[0] || "user";
      await _converseRef.api.rooms.open(roomJid, { nick });

      setConnected(true);
    } catch (e: any) {
      setError(e?.message || "Failed to connect");
      setConnected(false);
    } finally {
      setConnecting(false);
    }
  }

  async function send() {
    try {
      if (!connected) throw new Error("Not connected");
      const text = input.trim();
      if (!text) return;

      setInput("");

      const room = await _converseRef.api.rooms.get(roomJid);
      if (!room) throw new Error("Room not found (did join fail?)");

      room.sendMessage(text);

      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${Math.random()}`,
          from: "me",
          body: text,
          time: new Date().toLocaleTimeString(),
        },
      ]);
    } catch (e: any) {
      setError(e?.message || "Failed to send");
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/50 p-0 sm:p-6">
      <div className="flex h-[92vh] w-full flex-col bg-white shadow-xl sm:h-[80vh] sm:max-w-5xl sm:rounded-2xl">
        <div className="flex items-center justify-between border-b p-3 sm:p-4">
          <div className="text-base font-semibold sm:text-lg">Chat (Headless)</div>
          <button
            className="rounded-lg border px-3 py-1 text-sm hover:bg-gray-50"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="border-b bg-gray-50 p-3 sm:p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="flex-1">
                <label className="block text-xs font-medium text-gray-600">JID</label>
                <input
                  className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder={`andy@${XMPP_CONFIG.domain}`}
                  value={jid}
                  onChange={(e) => setJid(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && connect()}
                />
              </div>

              <div className="flex-1">
                <label className="block text-xs font-medium text-gray-600">Password</label>
                <input
                  className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && connect()}
                />
              </div>

              <div className="flex-1">
                <label className="block text-xs font-medium text-gray-600">Room</label>
                <input
                  className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
                  value={roomJid}
                  onChange={(e) => setRoomJid(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && connect()}
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
                  onClick={connect}
                  disabled={connecting}
                >
                  {connecting ? "Connecting…" : `Connect (${transportLabel})`}
                </button>
              </div>
            </div>

            {error && (
              <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {error}
              </div>
            )}

            {connected && (
              <div className="mt-2 text-xs text-green-700">Connected ✅ Joined: {roomJid}</div>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-auto p-3 sm:p-4">
            <div className="space-y-2">
              {messages.map((m) => (
                <div key={m.id} className="rounded-lg border p-2">
                  <div className="text-xs text-gray-500">
                    {m.time} • {m.from}
                  </div>
                  <div className="text-sm text-gray-900">{m.body}</div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          </div>

          <div className="border-t p-3 sm:p-4">
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-lg border px-3 py-2 text-sm"
                placeholder="Type a message…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()}
                disabled={!connected}
              />
              <button
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
                onClick={send}
                disabled={!connected}
              >
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

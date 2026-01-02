"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import XMPP_CONFIG from "@/lib/xmppConfig";

<<<<<<< HEAD
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
=======
type Message = {
  id: string;
  from: string;
  nick: string;
  body: string;
  timestamp: Date;
  isOwnMessage: boolean;
};

type ConnectionState = "disconnected" | "connecting" | "connected" | "error";

/**
 * ChatModal - XMPP MUC chat using Strophe.js
 *
 * This implementation uses Strophe.js directly instead of @converse/headless because:
 * - Simpler API that works naturally with React
 * - No plugin system complexity
 * - Better Next.js/Turbopack compatibility
 * - Smaller bundle size
 * - Direct control over XMPP connection
 */

export function ChatModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentNick, setCurrentNick] = useState<string>("user-" + Math.random().toString(36).substr(2, 9));

  const connectionRef = useRef<any>(null);
  const StropheRef = useRef<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);
>>>>>>> e7cb27ca3b7497f415c981a544f406a35b2bfe39

  // Load Strophe.js and connect
  useEffect(() => {
    setJid(localStorage.getItem("automatr_xmpp_jid") || "");
    setPassword(localStorage.getItem("automatr_xmpp_pw") || "");
  }, []);

<<<<<<< HEAD
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  useEffect(() => {
    if (!open) {
      setError(null);
      setConnecting(false);
    }
  }, [open]);
=======
    let mounted = true;

    // Dynamic import to avoid SSR issues
    import("strophe.js")
      .then((Strophe) => {
        if (!mounted) return;

        StropheRef.current = Strophe.Strophe;

        // Create connection
        const service = XMPP_CONFIG.useWebSocket ? XMPP_CONFIG.websocketUrl : XMPP_CONFIG.boshUrl;
        const connection = new Strophe.Strophe.Connection(service);

        connectionRef.current = connection;

        // Connection status callback
        const onConnect = (status: number) => {
          const Status = Strophe.Strophe.Status;

          switch (status) {
            case Status.CONNECTING:
              setConnectionState("connecting");
              setError(null);
              break;
            case Status.CONNECTED:
              setConnectionState("connected");
              setError(null);
              console.log("[XMPP] Connected");

              // Join MUC room after connecting
              joinRoom(connection, Strophe);
              break;
            case Status.DISCONNECTED:
              setConnectionState("disconnected");
              console.log("[XMPP] Disconnected");
              break;
            case Status.ERROR:
            case Status.CONNFAIL:
            case Status.AUTHFAIL:
              setConnectionState("error");
              setError("Failed to connect to XMPP server. Check your credentials and server settings.");
              console.error("[XMPP] Connection error");
              break;
          }
        };

        // Connect to XMPP server
        // For demo purposes, using anonymous auth. In production, use real credentials.
        const jid = `${currentNick}@${XMPP_CONFIG.domain}`;
        const password = ""; // Anonymous or use real password

        console.log("[XMPP] Connecting to", service, "as", jid);
        connection.connect(jid, password, onConnect);
      })
      .catch((err) => {
        console.error("[XMPP] Failed to load Strophe.js:", err);
        setError("Failed to load chat library");
      });

    // Cleanup on unmount or modal close
    return () => {
      mounted = false;
      if (connectionRef.current?.connected) {
        leaveRoom();
        connectionRef.current.disconnect();
      }
    };
  }, [open, currentNick]);

  // Join MUC room
  const joinRoom = (connection: any, Strophe: any) => {
    const roomJid = `${XMPP_CONFIG.defaultRoom}@${XMPP_CONFIG.mucDomain}`;
    const nick = currentNick;

    console.log("[MUC] Joining room", roomJid, "as", nick);

    // Add handler for MUC messages
    connection.addHandler(
      (stanza: Element) => onMessage(stanza, Strophe),
      null,
      "message",
      "groupchat",
      null,
      null
    );

    // Add handler for presence (optional, for roster)
    connection.addHandler(
      (stanza: Element) => onPresence(stanza, Strophe),
      null,
      "presence",
      null,
      null,
      roomJid,
      { matchBare: true }
    );

    // Send presence to join room
    const presence = new Strophe.Strophe.Builder("presence", {
      to: `${roomJid}/${nick}`,
    })
      .c("x", { xmlns: Strophe.Strophe.NS.MUC })
      .tree();

    connection.send(presence);
  };

  // Leave MUC room
  const leaveRoom = () => {
    if (!connectionRef.current || !StropheRef.current) return;

    const roomJid = `${XMPP_CONFIG.defaultRoom}@${XMPP_CONFIG.mucDomain}`;
    const nick = currentNick;

    const presence = new StropheRef.current.Builder("presence", {
      to: `${roomJid}/${nick}`,
      type: "unavailable",
    }).tree();

    connectionRef.current.send(presence);
  };

  // Handle incoming messages
  const onMessage = (stanza: Element, Strophe: any) => {
    const from = stanza.getAttribute("from");
    const type = stanza.getAttribute("type");
    const body = stanza.querySelector("body")?.textContent;

    if (!from || !body || type !== "groupchat") {
      return true; // Keep handler
    }

    // Extract nickname from full JID (room@domain/nick)
    const nick = Strophe.Strophe.getResourceFromJid(from);
    const isOwnMessage = nick === currentNick;

    // Avoid duplicate messages
    const messageId = stanza.getAttribute("id") || `msg-${Date.now()}-${Math.random()}`;

    setMessages((prev) => {
      // Check if we already have this message
      if (prev.some((m) => m.id === messageId)) {
        return prev;
      }

      return [
        ...prev,
        {
          id: messageId,
          from,
          nick: nick || "Unknown",
          body,
          timestamp: new Date(),
          isOwnMessage,
        },
      ];
    });

    return true; // Keep handler
  };

  // Handle presence updates (for roster, optional)
  const onPresence = (stanza: Element, Strophe: any) => {
    const from = stanza.getAttribute("from");
    const type = stanza.getAttribute("type");

    if (!from) return true;

    const nick = Strophe.Strophe.getResourceFromJid(from);

    if (type === "unavailable") {
      console.log("[MUC]", nick, "left the room");
    } else {
      console.log("[MUC]", nick, "joined the room");
    }

    return true; // Keep handler
  };

  // Send message
  const sendMessage = () => {
    if (!inputValue.trim() || !connectionRef.current || !StropheRef.current) return;
    if (connectionState !== "connected") return;

    const roomJid = `${XMPP_CONFIG.defaultRoom}@${XMPP_CONFIG.mucDomain}`;

    const message = new StropheRef.current.Builder("message", {
      to: roomJid,
      type: "groupchat",
    })
      .c("body")
      .t(inputValue.trim())
      .tree();

    connectionRef.current.send(message);
    setInputValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };
>>>>>>> e7cb27ca3b7497f415c981a544f406a35b2bfe39

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
<<<<<<< HEAD
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
=======
    <Modal open={open} onClose={onClose} title="Chat">
      <div className="flex h-[600px] max-h-[80vh]">
        {/* Sidebar */}
        <div
          className={`flex flex-col border-r border-gray-200 bg-gray-50 transition-all ${
            sidebarOpen ? "w-64" : "w-0"
          } overflow-hidden`}
        >
          <div className="flex items-center justify-between border-b border-gray-200 p-3">
            <h3 className="text-sm font-semibold text-gray-900">Rooms</h3>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="rounded p-1 hover:bg-gray-200 md:hidden"
              aria-label="Toggle sidebar"
            >
              {sidebarOpen ? "✕" : "☰"}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            <div className="mb-2 px-2 text-xs font-semibold uppercase text-gray-600">Active</div>
            <div className="mb-1 rounded bg-blue-100 px-3 py-2 text-sm text-blue-900">
              # {XMPP_CONFIG.defaultRoom}
            </div>
          </div>

          {/* Connection status */}
          <div className="border-t border-gray-200 p-3">
            <div className="flex items-center gap-2 text-xs">
              <div
                className={`h-2 w-2 rounded-full ${
                  connectionState === "connected"
                    ? "bg-green-500"
                    : connectionState === "connecting"
                      ? "bg-yellow-500 animate-pulse"
                      : "bg-gray-400"
                }`}
              />
              <span className="text-gray-600">
                {connectionState === "connected"
                  ? "Connected"
                  : connectionState === "connecting"
                    ? "Connecting..."
                    : "Disconnected"}
              </span>
            </div>
            <div className="mt-1 text-xs text-gray-500">as {currentNick}</div>
          </div>
        </div>

        {/* Main chat area */}
        <div className="flex flex-1 flex-col">
          {!sidebarOpen && (
            <div className="border-b border-gray-200 p-3 md:hidden">
              <button onClick={() => setSidebarOpen(true)} className="rounded p-1 hover:bg-gray-100">
                ☰
              </button>
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div className="border-b border-red-300 bg-red-50 p-3 text-sm text-red-800">
              <strong>Error:</strong> {error}
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto bg-white p-4">
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center text-gray-500">
                <div className="text-center">
                  <div className="mb-2 text-4xl">💬</div>
                  <div className="text-sm">
                    {connectionState === "connected"
                      ? "No messages yet. Start the conversation!"
                      : "Connecting to chat..."}
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex items-start gap-2 ${msg.isOwnMessage ? "flex-row-reverse" : ""}`}
                  >
                    <div
                      className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-xs font-medium text-white ${
                        msg.isOwnMessage ? "bg-blue-600" : "bg-gray-600"
                      }`}
                    >
                      {msg.nick.substring(0, 2).toUpperCase()}
                    </div>
                    <div className={`flex-1 ${msg.isOwnMessage ? "text-right" : ""}`}>
                      <div className="mb-1 text-xs text-gray-500">
                        {msg.nick} • {msg.timestamp.toLocaleTimeString()}
                      </div>
                      <div
                        className={`inline-block rounded-lg px-3 py-2 text-sm ${
                          msg.isOwnMessage ? "bg-blue-100 text-blue-900" : "bg-gray-100 text-gray-900"
                        }`}
                      >
                        {msg.body}
                      </div>
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
>>>>>>> e7cb27ca3b7497f415c981a544f406a35b2bfe39
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

<<<<<<< HEAD
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
=======
          {/* Input area */}
          <div className="border-t border-gray-200 bg-white p-4">
            <div className="flex gap-2">
              <input
                type="text"
                placeholder={
                  connectionState === "connected" ? "Type a message..." : "Connecting..."
                }
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:bg-gray-100 disabled:cursor-not-allowed"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={connectionState !== "connected"}
              />
              <button
                onClick={sendMessage}
                disabled={connectionState !== "connected" || !inputValue.trim()}
                className="rounded-lg border border-blue-600 bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Send
              </button>
            </div>
            <div className="mt-2 text-xs text-gray-500">
              Press Enter to send, Shift+Enter for new line
>>>>>>> e7cb27ca3b7497f415c981a544f406a35b2bfe39
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

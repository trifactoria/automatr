"use client";

import { useEffect, useRef, useState } from "react";
import { Modal } from "./Modal";
import XMPP_CONFIG from "@/lib/xmppConfig";

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
  const [currentNick, setCurrentNick] = useState<string>(process.env.NEXT_PUBLIC_XMPP_NICK || "andy");

  const connectionRef = useRef<any>(null);
  const StropheRef = useRef<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load Strophe.js and connect
  useEffect(() => {
    if (!open) return;

    let mounted = true;

    // Dynamic import to avoid SSR issues
    // The package.json exports field should resolve to browser bundle when ssr: false is used in page.tsx
    import("strophe.js")
      .then((mod) => {
        if (!mounted) return;

        const Strophe = (mod as any).Strophe;
        StropheRef.current = Strophe;

        // Create connection
        const service = XMPP_CONFIG.useWebSocket ? XMPP_CONFIG.websocketUrl : XMPP_CONFIG.boshUrl;
        const connection = new Strophe.Connection(service);

        connectionRef.current = connection;

        // Connection status callback
        const onConnect = (status: number) => {
          const Status = Strophe.Status;

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
        // IMPORTANT: JID is the ACCOUNT. The random string is only your MUC nick.
        const jid = `${XMPP_CONFIG.username}@${XMPP_CONFIG.domain}`;
        const password = XMPP_CONFIG.password;

        console.log("[XMPP] Connecting to", service, "as", jid, "nick:", currentNick);
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
    const presence = new Strophe.Builder("presence", {
      to: `${roomJid}/${nick}`,
    })
      .c("x", { xmlns: Strophe.NS.MUC })
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
    const nick = Strophe.getResourceFromJid(from);
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

    const nick = Strophe.getResourceFromJid(from);

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

  return (
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
              </div>
            )}
          </div>

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
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}

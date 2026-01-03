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

type Occupant = {
  nick: string;
  online: boolean;
};

export function ChatModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [joined, setJoined] = useState(false);

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [currentNick] = useState<string>(XMPP_CONFIG.username);

  const [rooms, setRooms] = useState<string[]>([XMPP_CONFIG.defaultRoom]);
  const [occupants, setOccupants] = useState<Occupant[]>([]);

  const connectionRef = useRef<any>(null);
  const StropheRef = useRef<any>(null);

  const pendingSendsRef = useRef<string[]>([]);
  const roomJoinAttemptRef = useRef(0);
  const handlersInstalledRef = useRef(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const roomBareJid = () => `${XMPP_CONFIG.defaultRoom}@${XMPP_CONFIG.mucDomain}`;

  function hasWebCryptoDeriveBits(): boolean {
    const subtle = (globalThis as any)?.crypto?.subtle;
    return !!subtle && typeof subtle.deriveBits === "function";
  }

  function forcePlainAuthHard(connection: any, Strophe: any) {
    // If WebCrypto exists, SCRAM is safe and we do nothing.
    if (hasWebCryptoDeriveBits()) return;

    console.warn("[XMPP] crypto.subtle missing; forcing PLAIN-only SASL");

    // 1) Disable known SCRAM mechanisms if API exists (older builds)
    try {
      if (typeof connection.deleteMechanism === "function") {
        connection.deleteMechanism("SCRAM-SHA-1");
        connection.deleteMechanism("SCRAM-SHA-256");
        connection.deleteMechanism("SCRAM-SHA-512");
      }
    } catch {}

    // 2) HARD OVERRIDE for strophe.browser.esm.js builds:
    // Replace connection.mechanisms so SASL selection cannot choose SCRAM.
    try {
      const plain =
        (Strophe as any)?.SASLPlain ||
        (Strophe as any)?.SASLMechanisms?.PLAIN ||
        null;

      if (!plain) {
        console.warn("[XMPP] Could not locate SASLPlain in Strophe build; auth may still fail.");
        return;
      }

      // Many builds store mechanisms here:
      connection.mechanisms = {
        PLAIN: plain,
      };

      // Some builds also track auth mechanisms list internally:
      if (Array.isArray((connection as any)._sasl_mechanisms)) {
        (connection as any)._sasl_mechanisms = ["PLAIN"];
      }

      // If there is a preferred list, set it:
      (connection as any).preferredSaslMechanism = "PLAIN";
    } catch (e) {
      console.warn("[XMPP] Failed to hard-force PLAIN mechanisms (ignored)", e);
    }

    // 3) Also scrub global registry just in case
    try {
      const mechs = (Strophe as any).SASLMechanisms;
      if (mechs) {
        for (const key of Object.keys(mechs)) {
          if (key.toUpperCase().includes("SCRAM")) delete mechs[key];
        }
      }
    } catch {}
  }

  useEffect(() => {
    if (!open) return;

    let mounted = true;

    setError(null);
    setMessages([]);
    setOccupants([]);
    setRooms([XMPP_CONFIG.defaultRoom]);
    setJoined(false);

    pendingSendsRef.current = [];
    roomJoinAttemptRef.current = 0;
    handlersInstalledRef.current = false;

    import("strophe.js")
      .then((mod) => {
        if (!mounted) return;

        const Strophe = (mod as any).Strophe;
        if (!Strophe) throw new Error("strophe.js did not export Strophe");
        StropheRef.current = Strophe;

        const service = XMPP_CONFIG.useWebSocket ? XMPP_CONFIG.websocketUrl : XMPP_CONFIG.boshUrl;
        const connection = new Strophe.Connection(service);

        // MUST happen before connect()
        forcePlainAuthHard(connection, Strophe);

        connectionRef.current = connection;

        const jid = `${XMPP_CONFIG.username}@${XMPP_CONFIG.domain}`;
        const password = XMPP_CONFIG.password;

        const onConnect = (status: number) => {
          try {
            const Status = Strophe.Status;

            switch (status) {
              case Status.CONNECTING:
                setConnectionState("connecting");
                setError(null);
                break;

              case Status.CONNECTED:
                setConnectionState("connected");
                setError(null);

                setJoined(false);
                pendingSendsRef.current = [];
                roomJoinAttemptRef.current = 0;
                handlersInstalledRef.current = false;

                console.log("[XMPP] Connected");

                connection.send(new Strophe.Builder("presence").tree());

                discoverRooms(connection, Strophe);
                joinRoom(connection, Strophe);
                break;

              case Status.DISCONNECTED:
                setConnectionState("disconnected");
                setJoined(false);
                console.log("[XMPP] Disconnected");
                break;

              case Status.ERROR:
              case Status.CONNFAIL:
              case Status.AUTHFAIL:
                setConnectionState("error");
                setJoined(false);
                setError("Failed to connect to XMPP server. Check your credentials and server settings.");
                console.error("[XMPP] Connection error");
                break;

              default:
                break;
            }
          } catch (e) {
            console.error("[XMPP] onConnect callback crashed:", e);
            setConnectionState("error");
            setError("XMPP connect callback crashed (see console).");
          }
        };

        console.log("[XMPP] service=", service);
        console.log("[XMPP] jid=", jid, "nick=", currentNick, "webcrypto=", hasWebCryptoDeriveBits());

        connection.connect(jid, password, onConnect);
      })
      .catch((err) => {
        console.error("[XMPP] Failed to load/connect Strophe:", err);
        setError(String(err?.message || err || "Failed to load chat library"));
        setConnectionState("error");
      });

    return () => {
      mounted = false;
      const conn = connectionRef.current;
      if (conn?.connected && StropheRef.current) {
        leaveRoom();
        conn.disconnect();
      }
      connectionRef.current = null;
      StropheRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const discoverRooms = (connection: any, Strophe: any) => {
    const mucService = XMPP_CONFIG.mucDomain;

    const iq = new Strophe.Builder("iq", {
      type: "get",
      to: mucService,
      id: `disco-items-${Date.now()}`,
    })
      .c("query", { xmlns: "http://jabber.org/protocol/disco#items" })
      .tree();

    connection.sendIQ(
      iq,
      (res: Element) => {
        try {
          const items = Array.from(res.getElementsByTagName("item"));
          const discovered = items
            .map((it) => it.getAttribute("jid") || "")
            .filter(Boolean)
            .map((jid) => {
              const at = jid.indexOf("@");
              return at > 0 ? jid.slice(0, at) : jid;
            })
            .filter(Boolean);

          setRooms((prev) => {
            const base = new Set<string>([...prev, XMPP_CONFIG.defaultRoom, ...discovered]);
            return Array.from(base).sort((a, b) => a.localeCompare(b));
          });

          console.log("[MUC] Discovered rooms:", discovered);
        } catch (e) {
          console.warn("[MUC] Failed to parse disco#items response", e);
        }
      },
      (err: Element) => {
        console.warn("[MUC] disco#items failed (rooms list will be minimal)", err);
      }
    );
  };

  const installHandlersOnce = (connection: any, Strophe: any) => {
    if (handlersInstalledRef.current) return;
    handlersInstalledRef.current = true;

    const roomJid = roomBareJid();

    connection.addHandler(
      (stanza: Element) => onMessage(stanza, Strophe),
      null,
      "message",
      "groupchat",
      null,
      roomJid,
      { matchBare: true }
    );

    connection.addHandler(
      (stanza: Element) => onPresence(stanza, Strophe),
      null,
      "presence",
      null,
      null,
      roomJid,
      { matchBare: true }
    );
  };

  const joinRoom = (connection: any, Strophe: any) => {
    const roomJid = roomBareJid();
    const nick = currentNick;

    installHandlersOnce(connection, Strophe);

    console.log("[MUC] Joining room", roomJid, "as", nick);

    const presence = new Strophe.Builder("presence", {
      to: `${roomJid}/${nick}`,
    })
      .c("x", { xmlns: Strophe.NS.MUC })
      .tree();

    connection.send(presence);

    roomJoinAttemptRef.current += 1;
    const attempt = roomJoinAttemptRef.current;

    setTimeout(() => {
      if (!connectionRef.current?.connected) return;
      if (!joined && attempt === roomJoinAttemptRef.current) {
        console.warn("[MUC] join not confirmed yet; retrying join");
        const retry = new Strophe.Builder("presence", { to: `${roomJid}/${nick}` })
          .c("x", { xmlns: Strophe.NS.MUC })
          .tree();
        connection.send(retry);
      }
    }, 2000);
  };

  const leaveRoom = () => {
    if (!connectionRef.current || !StropheRef.current) return;

    const roomJid = roomBareJid();
    const nick = currentNick;

    const presence = new StropheRef.current.Builder("presence", {
      to: `${roomJid}/${nick}`,
      type: "unavailable",
    }).tree();

    connectionRef.current.send(presence);
  };

  const sendGroupchat = (text: string) => {
    if (!connectionRef.current || !StropheRef.current) return;
    const roomJid = roomBareJid();

    const message = new StropheRef.current.Builder("message", {
      to: roomJid,
      type: "groupchat",
      id: `web-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    })
      .c("body")
      .t(text)
      .tree();

    connectionRef.current.send(message);
  };

  const onMessage = (stanza: Element, Strophe: any) => {
    const from = stanza.getAttribute("from");
    const type = stanza.getAttribute("type");
    const body = stanza.querySelector("body")?.textContent;

    if (!from || !body || type !== "groupchat") return true;

    const nick = Strophe.getResourceFromJid(from);
    const isOwnMessage = nick === currentNick;

    const messageId = stanza.getAttribute("id") || `msg-${Date.now()}-${Math.random()}`;

    setMessages((prev) => {
      if (prev.some((m) => m.id === messageId)) return prev;
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

    return true;
  };

  const onPresence = (stanza: Element, Strophe: any) => {
    const from = stanza.getAttribute("from");
    const type = stanza.getAttribute("type");
    if (!from) return true;

    const nick = Strophe.getResourceFromJid(from);
    if (!nick) return true;

    const online = type !== "unavailable";
    const bareFrom = Strophe.getBareJidFromJid(from);
    const roomJid = roomBareJid();

    if (bareFrom !== roomJid) return true;

    if (nick === currentNick && online) {
      const x = stanza.getElementsByTagNameNS("http://jabber.org/protocol/muc#user", "x")[0];
      if (x) {
        const statuses = x.getElementsByTagName("status");
        for (let i = 0; i < statuses.length; i++) {
          const code = statuses[i].getAttribute("code");
          if (code === "110") {
            if (!joined) {
              console.log("[MUC] Join confirmed (self-presence 110)");
              setJoined(true);

              const queued = pendingSendsRef.current.splice(0);
              queued.forEach((text) => sendGroupchat(text));
            }
            break;
          }
        }
      }
    }

    setOccupants((prev) => {
      const map = new Map(prev.map((o) => [o.nick, o]));
      if (!online) {
        map.delete(nick);
      } else {
        map.set(nick, { nick, online: true });
      }
      return Array.from(map.values()).sort((a, b) => {
        const aAgent = a.nick.startsWith("agent-") ? 0 : 1;
        const bAgent = b.nick.startsWith("agent-") ? 0 : 1;
        if (aAgent !== bAgent) return aAgent - bAgent;
        return a.nick.localeCompare(b.nick);
      });
    });

    return true;
  };

  const sendMessage = () => {
    const text = inputValue.trim();
    if (!text) return;

    if (connectionState !== "connected" || !connectionRef.current?.connected) return;

    if (!joined) {
      pendingSendsRef.current.push(text);
      setInputValue("");
      console.warn("[MUC] Not joined yet; queued message");
      return;
    }

    sendGroupchat(text);
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

            <div className="mb-2 rounded bg-blue-100 px-3 py-2 text-sm text-blue-900">
              # {XMPP_CONFIG.defaultRoom}
            </div>

            {rooms.length > 1 && (
              <>
                <div className="mb-2 px-2 text-xs font-semibold uppercase text-gray-600">Rooms</div>
                <div className="space-y-1">
                  {rooms
                    .filter((r) => r !== XMPP_CONFIG.defaultRoom)
                    .map((r) => (
                      <div key={r} className="mb-1 rounded bg-gray-100 px-3 py-2 text-sm text-gray-900">
                        # {r}
                      </div>
                    ))}
                </div>
              </>
            )}

            <div className="mt-4 mb-2 px-2 text-xs font-semibold uppercase text-gray-600">Online</div>
            {occupants.length === 0 ? (
              <div className="px-3 py-2 text-sm text-gray-500">No one else online</div>
            ) : (
              <div className="space-y-1">
                {occupants.map((o) => (
                  <div key={o.nick} className="flex items-center gap-2 rounded bg-white px-3 py-2 text-sm text-gray-900">
                    <div className="h-2 w-2 rounded-full bg-green-500" />
                    <span className="truncate">{o.nick}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-gray-200 p-3">
            <div className="flex items-center gap-2 text-xs">
              <div
                className={`h-2 w-2 rounded-full ${
                  connectionState === "connected"
                    ? joined
                      ? "bg-green-500"
                      : "bg-yellow-500 animate-pulse"
                    : connectionState === "connecting"
                      ? "bg-yellow-500 animate-pulse"
                      : "bg-gray-400"
                }`}
              />
              <span className="text-gray-600">
                {connectionState === "connected"
                  ? joined
                    ? "Connected"
                    : "Joining room..."
                  : connectionState === "connecting"
                    ? "Connecting..."
                    : "Disconnected"}
              </span>
            </div>
            <div className="mt-1 text-xs text-gray-500">as {currentNick}</div>
          </div>
        </div>

        <div className="flex flex-1 flex-col">
          {!sidebarOpen && (
            <div className="border-b border-gray-200 p-3 md:hidden">
              <button onClick={() => setSidebarOpen(true)} className="rounded p-1 hover:bg-gray-100">
                ☰
              </button>
            </div>
          )}

          {error && (
            <div className="border-b border-red-300 bg-red-50 p-3 text-sm text-red-800">
              <strong>Error:</strong> {error}
            </div>
          )}

          <div className="flex-1 overflow-y-auto bg-white p-4">
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center text-gray-500">
                <div className="text-center">
                  <div className="mb-2 text-4xl">💬</div>
                  <div className="text-sm">
                    {connectionState === "connected"
                      ? joined
                        ? "No messages yet. Start the conversation!"
                        : "Joining room..."
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

          <div className="border-t border-gray-200 bg-white p-4">
            <div className="flex gap-2">
              <input
                type="text"
                placeholder={
                  connectionState === "connected" ? (joined ? "Type a message..." : "Joining room...") : "Connecting..."
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
            <div className="mt-2 text-xs text-gray-500">Press Enter to send, Shift+Enter for new line</div>
          </div>
        </div>
      </div>
    </Modal>
  );
}

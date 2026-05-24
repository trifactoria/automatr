// src/components/ChatModal.tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Modal } from "./Modal";
import XMPP_CONFIG from "@/lib/xmppConfig";
import { deriveXmppTransportUrlsFromWindow } from "@/lib/xmppServiceUrl";
import {
  disableScramMechanismsIfNoWebCrypto,
  hasWebCryptoDeriveBits,
  nowId,
  safeLower,
} from "@/lib/xmppStropheUtil";
import type { Connection, Strophe as StropheClass } from "strophe.js";

type Message = {
  id: string;
  from: string;
  nick: string;
  body: string;
  timestamp: Date;
  isOwnMessage: boolean;
  kind: "room" | "dm";
  room: string; // room node context
  dmJid?: string; // when kind==="dm"
};

type ConnectionState = "disconnected" | "connecting" | "connected" | "error";
type Occupant = { nick: string; online: boolean };
type RoomInfo = { name: string }; // node only
type StropheApi = typeof StropheClass;

type ChatTarget =
  | { kind: "room"; room: string }
  | { kind: "dm"; room: string; nick: string; jid: string };

export function ChatModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [joined, setJoined] = useState(false);

  // UI state
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false); // mobile-first
  const [error, setError] = useState<string | null>(null);

  const [rooms, setRooms] = useState<RoomInfo[]>([{ name: XMPP_CONFIG.defaultRoom }]);
  const [roomInput, setRoomInput] = useState("");
  const [occupants, setOccupants] = useState<Occupant[]>([]);

  const [currentNick] = useState<string>(XMPP_CONFIG.username);

  // Default to room
  const [target, setTarget] = useState<ChatTarget>({
    kind: "room",
    room: XMPP_CONFIG.defaultRoom,
  });

  // Strophe refs
  const connectionRef = useRef<Connection | null>(null);
  const StropheRef = useRef<StropheApi | null>(null);

  // misc refs
  const handlersInstalledRef = useRef(false);
  const joinedRef = useRef(false);
  const activeRoomRef = useRef(XMPP_CONFIG.defaultRoom);
  const targetRef = useRef<ChatTarget>({ kind: "room", room: XMPP_CONFIG.defaultRoom });

  const pendingRoomSendsRef = useRef<string[]>([]);
  const pendingDmSendsRef = useRef<{ room: string; nick: string; jid: string; text: string }[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Derived helpers (addressing)
  const domain = XMPP_CONFIG.domain;
  const mucDomain = XMPP_CONFIG.mucDomain;

  const roomBareJidFor = (roomNode: string) => `${roomNode}@${mucDomain}`;
  const myJid = `${XMPP_CONFIG.username}@${domain}`;
  const directJidForNick = (nick: string) => `${nick}@${domain}`;

  const headerTitle = useMemo(() => {
    if (target.kind === "room") return `# ${target.room}`;
    return `DM: ${target.nick}  (${target.jid})`;
  }, [target]);

  useEffect(() => {
    targetRef.current = target;
  }, [target]);

  useEffect(() => {
    activeRoomRef.current = target.room;
  }, [target]);

  useEffect(() => {
    joinedRef.current = joined;
  }, [joined]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function installHandlersOnce(connection: Connection, Strophe: StropheApi) {
    if (handlersInstalledRef.current) return;
    handlersInstalledRef.current = true;

    // Groupchat messages for ANY room
    connection.addHandler(
      (stanza: Element) => onMessage(stanza, Strophe),
      null,
      "message",
      "groupchat",
      null,
      null,
      { matchBare: true }
    );

    // Chat messages (direct DMs + possibly server echoes)
    connection.addHandler(
      (stanza: Element) => onMessage(stanza, Strophe),
      null,
      "message",
      "chat",
      null,
      null,
      { matchBare: true }
    );

    // Presence updates (filter to active room inside handler)
    connection.addHandler(
      (stanza: Element) => onPresence(stanza, Strophe),
      null,
      "presence",
      null,
      null,
      null,
      { matchBare: true }
    );
  }

  function sendPresenceAvailable(connection: Connection, Strophe: StropheApi) {
    connection.send(new Strophe.Builder("presence").tree());
  }

  function sendRoomJoin(connection: Connection, Strophe: StropheApi, roomNode: string, nick: string) {
    const roomJid = roomBareJidFor(roomNode);
    console.log("[MUC] Joining room", roomJid, "as", nick);
    const presence = new Strophe.Builder("presence", { to: `${roomJid}/${nick}` })
      .c("x", { xmlns: Strophe.NS.MUC })
      .tree();
    connection.send(presence);
  }

  function sendRoomLeave(connection: Connection, Strophe: StropheApi, roomNode: string, nick: string) {
    const roomJid = roomBareJidFor(roomNode);
    console.log("[MUC] Leaving room", roomJid, "as", nick);
    const presence = new Strophe.Builder("presence", { to: `${roomJid}/${nick}`, type: "unavailable" }).tree();
    connection.send(presence);
  }

  function sendGroupchat(connection: Connection, Strophe: StropheApi, roomNode: string, text: string) {
    const roomJid = roomBareJidFor(roomNode);
    const msg = new Strophe.Builder("message", {
      to: roomJid,
      type: "groupchat",
      id: nowId("web"),
    })
      .c("body")
      .t(text)
      .tree();

    connection.send(msg);
  }

  function sendDirectChat(connection: Connection, Strophe: StropheApi, toJid: string, text: string) {
    const msg = new Strophe.Builder("message", {
      to: toJid,
      type: "chat",
      id: nowId("dm"),
    })
      .c("body")
      .t(text)
      .tree();

    connection.send(msg);
  }

  function discoverRooms(connection: Connection, Strophe: StropheApi) {
    const mucService = mucDomain;

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
          const discoveredNodes = items
            .map((it) => it.getAttribute("jid") || "")
            .filter(Boolean)
            .map((jid) => {
              const at = jid.indexOf("@");
              return at > 0 ? jid.slice(0, at) : jid;
            })
            .filter(Boolean);

          const merged = new Set<string>([
            XMPP_CONFIG.defaultRoom,
            ...rooms.map((r) => r.name),
            ...discoveredNodes,
          ]);

          setRooms(Array.from(merged).sort((a, b) => a.localeCompare(b)).map((name) => ({ name })));
          console.log("[MUC] Discovered rooms:", discoveredNodes);
        } catch (e) {
          console.warn("[MUC] Failed to parse disco#items response", e);
        }
      },
      (err: Element) => {
        console.warn("[MUC] disco#items failed (rooms list will be minimal)", err);
      }
    );
  }

  function switchRoom(newRoom: string) {
    const roomNode = (newRoom || "").trim();
    if (!roomNode) return;

    setRooms((prev) => {
      const s = new Set(prev.map((r) => r.name));
      s.add(roomNode);
      return Array.from(s).sort((a, b) => a.localeCompare(b)).map((name) => ({ name }));
    });

    setTarget({ kind: "room", room: roomNode });
    setMessages([]);
    setOccupants([]);
    setJoined(false);
    joinedRef.current = false;

    const conn = connectionRef.current;
    const Strophe = StropheRef.current;
    if (!conn || !Strophe || !conn.connected) return;

    const oldRoom = activeRoomRef.current;
    if (oldRoom && oldRoom !== roomNode) {
      sendRoomLeave(conn, Strophe, oldRoom, currentNick);
    }

    sendRoomJoin(conn, Strophe, roomNode, currentNick);
    discoverRooms(conn, Strophe);

    setSidebarOpen(false);
  }

  function openDm(nick: string) {
    const n = (nick || "").trim();
    if (!n) return;

    const roomNode = activeRoomRef.current || XMPP_CONFIG.defaultRoom;
    const jid = directJidForNick(n);

    setTarget({ kind: "dm", room: roomNode, nick: n, jid });
    setMessages([]);
    setError(null);
    setSidebarOpen(false);
  }

  function backToRoom() {
    const roomNode = activeRoomRef.current || XMPP_CONFIG.defaultRoom;
    setTarget({ kind: "room", room: roomNode });
    setMessages([]);
    setError(null);
  }

  function appendOptimisticOutgoing(text: string) {
    const t = targetRef.current;
    const kind: "room" | "dm" = t.kind === "room" ? "room" : "dm";
    const roomNode = t.room;
    const dmJid = t.kind === "dm" ? t.jid : undefined;

    setMessages((prev) => [
      ...prev,
      {
        id: nowId(kind === "room" ? "out-room" : "out-dm"),
        from: myJid,
        nick: currentNick,
        body: text,
        timestamp: new Date(),
        isOwnMessage: true,
        kind,
        room: roomNode,
        dmJid,
      },
    ]);
  }

  function sendCurrent(text: string) {
    const conn = connectionRef.current;
    const Strophe = StropheRef.current;
    if (!conn || !Strophe || !conn.connected) return;

    const t = targetRef.current;

    // always show what we sent
    appendOptimisticOutgoing(text);

    // room: wait for join
    if (t.kind === "room" && !joinedRef.current) {
      pendingRoomSendsRef.current.push(text);
      console.warn("[MUC] Not joined yet; queued room message");
      return;
    }

    // dm: queue until join too (keeps behavior predictable)
    if (t.kind === "dm" && !joinedRef.current) {
      pendingDmSendsRef.current.push({ room: t.room, nick: t.nick, jid: t.jid, text });
      console.warn("[DM] Not joined yet; queued DM");
      return;
    }

    if (t.kind === "room") sendGroupchat(conn, Strophe, t.room, text);
    else sendDirectChat(conn, Strophe, t.jid, text);
  }

  function onMessage(stanza: Element, Strophe: StropheApi) {
    const from = stanza.getAttribute("from") || "";
    const type = stanza.getAttribute("type") || "";
    const body = stanza.querySelector("body")?.textContent || "";
    if (!body) return true;

    const t = targetRef.current;

    // -------- groupchat (room stream) --------
    if (type === "groupchat") {
      const bareFrom = Strophe.getBareJidFromJid(from); // room@conference.domain
      const nick = Strophe.getResourceFromJid(from) || "";
      if (!bareFrom.includes("@")) return true;
      if (!safeLower(bareFrom).endsWith(`@${safeLower(mucDomain)}`)) return true;

      const roomNode = bareFrom.split("@")[0] || "";
      if (t.kind !== "room") return true;
      if (t.room !== roomNode) return true;

      const isOwn = nick === currentNick;
      const id = stanza.getAttribute("id") || nowId(`msg-room-${roomNode}-${nick}`);

      setMessages((prev) => {
        if (prev.some((m) => m.id === id)) return prev;
        return [
          ...prev,
          {
            id,
            from,
            nick: nick || "Unknown",
            body,
            timestamp: new Date(),
            isOwnMessage: isOwn,
            kind: "room",
            room: roomNode,
          },
        ];
      });

      return true;
    }

    // -------- chat (direct DM) --------
    if (type === "chat") {
      if (t.kind !== "dm") return true;

      const bareFrom = Strophe.getBareJidFromJid(from);
      const myBare = Strophe.getBareJidFromJid(myJid);
      const targetBare = Strophe.getBareJidFromJid(t.jid);

      const isFromTarget = safeLower(bareFrom) === safeLower(targetBare);
      const isFromMe = safeLower(bareFrom) === safeLower(myBare);

      if (!isFromTarget && !isFromMe) return true;

      const displayNick = isFromMe ? currentNick : t.nick;
      const isOwn = isFromMe;

      const id = stanza.getAttribute("id") || nowId(`msg-dm-${displayNick}`);

      setMessages((prev) => {
        if (prev.some((m) => m.id === id)) return prev;
        return [
          ...prev,
          {
            id,
            from,
            nick: displayNick || "Unknown",
            body,
            timestamp: new Date(),
            isOwnMessage: isOwn,
            kind: "dm",
            room: t.room,
            dmJid: targetBare,
          },
        ];
      });

      return true;
    }

    return true;
  }

  function onPresence(stanza: Element, Strophe: StropheApi) {
    const from = stanza.getAttribute("from") || "";
    const type = stanza.getAttribute("type") || "";
    if (!from) return true;

    // room presence: room@conference.domain/nick
    const bareFrom = Strophe.getBareJidFromJid(from);
    const nick = Strophe.getResourceFromJid(from) || "";
    if (!nick) return true;

    if (!safeLower(bareFrom).endsWith(`@${safeLower(mucDomain)}`)) return true;

    const roomNode = bareFrom.split("@")[0] || "";
    const activeRoom = activeRoomRef.current;

    if (roomNode !== activeRoom) return true;

    const online = type !== "unavailable";

    // self-presence join confirmation (110)
    if (nick === currentNick && online) {
      const x = stanza.getElementsByTagNameNS("http://jabber.org/protocol/muc#user", "x")[0];
      if (x) {
        const statuses = x.getElementsByTagName("status");
        for (let i = 0; i < statuses.length; i++) {
          const code = statuses[i].getAttribute("code");
          if (code === "110") {
            if (!joinedRef.current) {
              console.log("[MUC] Join confirmed (self-presence 110) room=", activeRoom);
              setJoined(true);

              // flush queued room
              const roomQueued = pendingRoomSendsRef.current.splice(0);
              roomQueued.forEach((text) => {
                const conn = connectionRef.current;
                const S = StropheRef.current;
                if (conn && S && conn.connected) sendGroupchat(conn, S, activeRoomRef.current, text);
              });

              // flush queued dm
              const dmQueued = pendingDmSendsRef.current.splice(0);
              dmQueued.forEach((q) => {
                const conn = connectionRef.current;
                const S = StropheRef.current;
                if (conn && S && conn.connected) sendDirectChat(conn, S, q.jid, q.text);
              });
            }
            break;
          }
        }
      }
    }

    setOccupants((prev) => {
      const map = new Map(prev.map((o) => [o.nick, o]));
      if (!online) map.delete(nick);
      else map.set(nick, { nick, online: true });

      return Array.from(map.values()).sort((a, b) => {
        const aIsMe = a.nick === currentNick ? 1 : 0;
        const bIsMe = b.nick === currentNick ? 1 : 0;
        if (aIsMe !== bIsMe) return aIsMe - bIsMe;

        const aAgent = a.nick.startsWith("agent-") ? 0 : 1;
        const bAgent = b.nick.startsWith("agent-") ? 0 : 1;
        if (aAgent !== bAgent) return aAgent - bAgent;
        return a.nick.localeCompare(b.nick);
      });
    });

    return true;
  }

  useEffect(() => {
    if (!open) return;

    let mounted = true;

    // reset UI state on open
    setError(null);
    setMessages([]);
    setOccupants([]);
    setRooms([{ name: XMPP_CONFIG.defaultRoom }]);
    setJoined(false);
    setConnectionState("disconnected");
    setRoomInput("");

    // reset refs
    handlersInstalledRef.current = false;
    joinedRef.current = false;
    activeRoomRef.current = XMPP_CONFIG.defaultRoom;
    targetRef.current = { kind: "room", room: XMPP_CONFIG.defaultRoom };
    setTarget({ kind: "room", room: XMPP_CONFIG.defaultRoom });

    pendingRoomSendsRef.current = [];
    pendingDmSendsRef.current = [];

    import("strophe.js")
      .then((mod) => {
        if (!mounted) return;

        const Strophe = mod.Strophe;
        if (!Strophe) throw new Error("strophe.js did not export Strophe");
        StropheRef.current = Strophe;

        disableScramMechanismsIfNoWebCrypto(Strophe);

        // ✅ KEY FIX: derive transport URLs from the page origin (tail domain vs xps.local)
        const derived = deriveXmppTransportUrlsFromWindow();
        const service = XMPP_CONFIG.useWebSocket ? derived.websocketUrl : derived.boshUrl;

        console.log("[XMPP] page=", derived.origin);
        console.log("[XMPP] derived ws=", derived.websocketUrl);
        console.log("[XMPP] derived bosh=", derived.boshUrl);
        console.log("[XMPP] service=", service);
        console.log("[XMPP] jid=", myJid);
        console.log("[XMPP] domain=", domain, "mucDomain=", mucDomain);
        console.log("[XMPP] webcrypto=", hasWebCryptoDeriveBits());

        const connection = new Strophe.Connection(service);
        connectionRef.current = connection;

        installHandlersOnce(connection, Strophe);

        const onConnect = (status: number) => {
          try {
            const Status = Strophe.Status;
            switch (status) {
              case Status.CONNECTING:
                setConnectionState("connecting");
                setError(null);
                break;

              case Status.CONNECTED: {
                setConnectionState("connected");
                setError(null);

                console.log("[XMPP] Connected");
                sendPresenceAvailable(connection, Strophe);

                discoverRooms(connection, Strophe);

                const startRoom = activeRoomRef.current || XMPP_CONFIG.defaultRoom;
                sendRoomJoin(connection, Strophe, startRoom, currentNick);
                break;
              }

              case Status.DISCONNECTED:
                setConnectionState("disconnected");
                setJoined(false);
                setOccupants([]);
                console.log("[XMPP] Disconnected");
                break;

              case Status.ERROR:
              case Status.CONNFAIL:
              case Status.AUTHFAIL:
                setConnectionState("error");
                setJoined(false);
                setError("Failed to connect to XMPP server. Check credentials / URL / TLS.");
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

        connection.connect(myJid, XMPP_CONFIG.password, onConnect);
      })
      .catch((err) => {
        console.error("[XMPP] Failed to load/connect Strophe:", err);
        setError(String(err?.message || err || "Failed to load chat library"));
        setConnectionState("error");
      });

    return () => {
      mounted = false;
      try {
        const conn = connectionRef.current;
        const Strophe = StropheRef.current;
        if (conn?.connected && Strophe) {
          const roomNode = activeRoomRef.current || XMPP_CONFIG.defaultRoom;
          sendRoomLeave(conn, Strophe, roomNode, currentNick);
          conn.disconnect();
        }
      } catch {
        // ignore
      } finally {
        connectionRef.current = null;
        StropheRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const sendMessage = () => {
    const text = inputValue.trim();
    if (!text) return;

    if (connectionState !== "connected" || !connectionRef.current?.connected) return;

    sendCurrent(text);
    setInputValue("");
  };

  const activeRoom = target.room;

  return (
    <Modal open={open} onClose={onClose} title="Chat">
      <div className="flex h-[600px] max-h-[80vh]">
        {/* Mobile backdrop */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/30 md:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Sidebar drawer (mobile) + fixed column (desktop) */}
        <div
          className={[
            "md:relative md:z-auto md:flex md:w-72 md:translate-x-0",
            "fixed inset-y-0 left-0 z-50 w-72 transform transition-transform md:transform-none",
            sidebarOpen ? "translate-x-0" : "-translate-x-full",
            "flex flex-col border-r border-gray-200 bg-gray-50",
          ].join(" ")}
        >
          <div className="flex items-center justify-between border-b border-gray-200 p-3">
            <h3 className="text-sm font-semibold text-gray-900">Rooms</h3>
            <button
              onClick={() => setSidebarOpen(false)}
              className="rounded p-1 hover:bg-gray-200 md:hidden"
              aria-label="Close sidebar"
              title="Close sidebar"
            >
              ✕
            </button>
          </div>

          {/* Join room input */}
          <div className="border-b border-gray-200 p-3">
            <div className="text-xs font-semibold uppercase text-gray-600 mb-2">Join / Switch room</div>
            <div className="flex gap-2">
              <input
                value={roomInput}
                onChange={(e) => setRoomInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    const r = roomInput.trim();
                    if (r) {
                      switchRoom(r);
                      setRoomInput("");
                    }
                  }
                }}
                placeholder="room name (e.g. automatr)"
                className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
              />
              <button
                onClick={() => {
                  const r = roomInput.trim();
                  if (!r) return;
                  switchRoom(r);
                  setRoomInput("");
                }}
                className="rounded border border-gray-300 bg-white px-2 py-1 text-sm hover:bg-gray-100"
              >
                Go
              </button>
            </div>
            <div className="mt-2 text-[11px] text-gray-500">
              Tip: Prosody disco may return empty until rooms are created. You can still join any room name.
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            <div className="mb-2 px-2 text-xs font-semibold uppercase text-gray-600">Active</div>

            <div className="mb-2 rounded bg-blue-100 px-3 py-2 text-sm text-blue-900 flex items-center justify-between">
              <span># {activeRoom}</span>
              {target.kind === "dm" && (
                <button onClick={backToRoom} className="text-xs underline">
                  back
                </button>
              )}
            </div>

            {/* Rooms list */}
            <div className="mb-2 px-2 text-xs font-semibold uppercase text-gray-600">Rooms</div>
            <div className="space-y-1">
              {rooms.map((r) => {
                const isActive = r.name === activeRoom && target.kind === "room";
                return (
                  <button
                    key={r.name}
                    onClick={() => switchRoom(r.name)}
                    className={`w-full text-left rounded px-3 py-2 text-sm ${
                      isActive ? "bg-blue-50 text-blue-900" : "bg-white hover:bg-gray-100 text-gray-900"
                    } border border-gray-200`}
                    title={`Join #${r.name}`}
                  >
                    # {r.name}
                  </button>
                );
              })}
            </div>

            {/* Online list */}
            <div className="mt-4 mb-2 px-2 text-xs font-semibold uppercase text-gray-600">Online</div>
            {occupants.length === 0 ? (
              <div className="px-3 py-2 text-sm text-gray-500">No one else online</div>
            ) : (
              <div className="space-y-1">
                {occupants.map((o) => {
                  const isMe = o.nick === currentNick;
                  const isDmActive = target.kind === "dm" && target.nick === o.nick;
                  return (
                    <div
                      key={o.nick}
                      className={`flex items-center gap-2 rounded px-3 py-2 text-sm border ${
                        isDmActive ? "bg-blue-50 border-blue-200" : "bg-white border-gray-200"
                      }`}
                    >
                      <div className="h-2 w-2 rounded-full bg-green-500" />
                      <button
                        className="truncate flex-1 text-left hover:underline"
                        onClick={() => {
                          if (isMe) return;
                          openDm(o.nick);
                        }}
                        title={isMe ? "That's you" : `DM ${o.nick}`}
                      >
                        {o.nick}
                        {isMe ? " (you)" : ""}
                      </button>
                      {!isMe && (
                        <button
                          onClick={() => openDm(o.nick)}
                          className="rounded border border-gray-300 bg-white px-2 py-0.5 text-xs hover:bg-gray-100"
                          title={`Open DM with ${o.nick}`}
                        >
                          DM
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Connection status */}
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
                  : connectionState === "error"
                  ? "Error"
                  : "Disconnected"}
              </span>
            </div>
            <div className="mt-1 text-xs text-gray-500">as {currentNick}</div>
          </div>
        </div>

        {/* Main */}
        <div className="flex flex-1 flex-col">
          {/* Header */}
          <div className="border-b border-gray-200 bg-white px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSidebarOpen((v) => !v)}
                className="md:hidden rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-50"
                aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
                title={sidebarOpen ? "Close sidebar" : "Open sidebar"}
              >
                {sidebarOpen ? "✕" : "☰"}
              </button>

              <div className="font-semibold text-gray-900 text-sm">{headerTitle}</div>
            </div>

            {target.kind === "dm" && (
              <button onClick={backToRoom} className="text-xs rounded border border-gray-300 px-2 py-1 hover:bg-gray-50">
                Back to room
              </button>
            )}
          </div>

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
                      title={msg.nick}
                    >
                      {msg.nick.substring(0, 2).toUpperCase()}
                    </div>
                    <div className={`flex-1 ${msg.isOwnMessage ? "text-right" : ""}`}>
                      <div className="mb-1 text-xs text-gray-500">
                        {msg.nick} • {msg.timestamp.toLocaleTimeString()}
                        {msg.kind === "dm" ? <span className="ml-2">(DM)</span> : null}
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

          {/* Composer */}
          <div className="border-t border-gray-200 bg-white p-4">
            <div className="flex gap-2">
              <input
                type="text"
                placeholder={
                  connectionState === "connected"
                    ? joined
                      ? target.kind === "dm"
                        ? `Message ${target.nick}…`
                        : "Type a message…"
                      : "Joining room…"
                    : "Connecting…"
                }
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:bg-gray-100 disabled:cursor-not-allowed"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
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
              Enter to send • Shift+Enter for new line • Click a user to open a DM • Use the room box to switch rooms
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}

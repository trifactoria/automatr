"use client";

import { useEffect, useRef, useState } from "react";
import { Modal } from "./Modal";
import XMPP_CONFIG from "@/lib/xmppConfig";

/**
 * ChatModal - Embeds converse.js for XMPP chat
 *
 * To enable full chat functionality:
 * 1. Install converse.js: npm install @conversejs/headless
 * 2. Uncomment the converse initialization code below
 * 3. Import converse styles in your global CSS or here
 *
 * Current implementation shows a placeholder UI with proper layout structure
 */

export function ChatModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const converseRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null);

  // Placeholder data (replace with actual converse.js data)
  const rooms = [
    { jid: `${XMPP_CONFIG.defaultRoom}@${XMPP_CONFIG.mucDomain}`, name: "Automatr" },
    { jid: `general@${XMPP_CONFIG.mucDomain}`, name: "General" },
  ];

  const contacts = [
    { jid: `agent1@${XMPP_CONFIG.domain}`, name: "Agent 1" },
    { jid: `agent2@${XMPP_CONFIG.domain}`, name: "Agent 2" },
  ];

  useEffect(() => {
    if (!open) return;

    // TODO: Initialize converse.js when installed
    // Example initialization (uncomment when converse.js is installed):
    /*
    import('@conversejs/headless').then((converse) => {
      if (converseRef.current) return; // Already initialized

      converse.initialize({
        websocket_url: XMPP_CONFIG.websocketUrl,
        bosh_service_url: XMPP_CONFIG.useWebSocket ? undefined : XMPP_CONFIG.boshUrl,
        jid: 'user@' + XMPP_CONFIG.domain, // Get from auth
        password: 'password', // Get from auth
        domain: XMPP_CONFIG.domain,
        auto_login: true,
        auto_join_rooms: [
          `${XMPP_CONFIG.defaultRoom}@${XMPP_CONFIG.mucDomain}`
        ],
        view_mode: 'embedded',
      });

      converseRef.current = converse;
    });
    */

    // Cleanup
    return () => {
      // TODO: Cleanup converse if needed
    };
  }, [open]);

  return (
    <Modal open={open} onClose={onClose} title="Chat">
      <div className="flex h-[600px] max-h-[80vh]">
        {/* Sidebar - Rooms & Contacts */}
        <div
          className={`flex flex-col border-r border-gray-200 bg-gray-50 transition-all ${
            sidebarOpen ? "w-64" : "w-0"
          } overflow-hidden`}
        >
          {/* Sidebar toggle button (mobile) */}
          <div className="flex items-center justify-between border-b border-gray-200 p-3">
            <h3 className="text-sm font-semibold text-gray-900">Conversations</h3>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="rounded p-1 hover:bg-gray-200 md:hidden"
              aria-label="Toggle sidebar"
            >
              {sidebarOpen ? "✕" : "☰"}
            </button>
          </div>

          {/* Rooms section */}
          <div className="flex-1 overflow-y-auto">
            <div className="p-2">
              <div className="mb-2 px-2 text-xs font-semibold uppercase text-gray-600">Rooms</div>
              {rooms.map((room) => (
                <button
                  key={room.jid}
                  onClick={() => setSelectedRoom(room.jid)}
                  className={`mb-1 w-full rounded px-3 py-2 text-left text-sm ${
                    selectedRoom === room.jid
                      ? "bg-blue-100 text-blue-900"
                      : "text-gray-700 hover:bg-gray-100"
                  }`}
                >
                  # {room.name}
                </button>
              ))}
            </div>

            {/* Contacts section */}
            <div className="p-2">
              <div className="mb-2 px-2 text-xs font-semibold uppercase text-gray-600">Direct Messages</div>
              {contacts.map((contact) => (
                <button
                  key={contact.jid}
                  onClick={() => setSelectedRoom(contact.jid)}
                  className={`mb-1 w-full rounded px-3 py-2 text-left text-sm ${
                    selectedRoom === contact.jid
                      ? "bg-blue-100 text-blue-900"
                      : "text-gray-700 hover:bg-gray-100"
                  }`}
                >
                  <span className="mr-2">●</span>
                  {contact.name}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Main chat area */}
        <div className="flex flex-1 flex-col">
          {/* Hamburger for mobile when sidebar closed */}
          {!sidebarOpen && (
            <div className="border-b border-gray-200 p-3 md:hidden">
              <button
                onClick={() => setSidebarOpen(true)}
                className="rounded p-1 hover:bg-gray-100"
                aria-label="Open sidebar"
              >
                ☰
              </button>
            </div>
          )}

          {/* Chat header */}
          {selectedRoom && (
            <div className="border-b border-gray-200 bg-white px-4 py-3">
              <h2 className="text-sm font-semibold text-gray-900">
                {rooms.find((r) => r.jid === selectedRoom)?.name ||
                  contacts.find((c) => c.jid === selectedRoom)?.name ||
                  selectedRoom}
              </h2>
            </div>
          )}

          {/* Messages area */}
          <div ref={containerRef} className="flex-1 overflow-y-auto bg-white p-4">
            {!selectedRoom ? (
              <div className="flex h-full items-center justify-center text-gray-500">
                <div className="text-center">
                  <div className="mb-2 text-4xl">💬</div>
                  <div className="text-sm">Select a room or contact to start chatting</div>
                  <div className="mt-4 rounded-lg bg-yellow-50 p-4 text-xs text-yellow-800">
                    <strong>Note:</strong> Install converse.js to enable full chat functionality:
                    <br />
                    <code className="mt-2 block rounded bg-yellow-100 p-2">
                      npm install @conversejs/headless
                    </code>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Placeholder messages */}
                <div className="flex items-start gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500 text-xs text-white">
                    A1
                  </div>
                  <div className="flex-1">
                    <div className="mb-1 text-xs text-gray-500">Agent 1 • 10:30 AM</div>
                    <div className="rounded-lg bg-gray-100 p-2 text-sm">
                      This is a placeholder message. Install converse.js to see real messages.
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input area */}
          {selectedRoom && (
            <div className="border-t border-gray-200 bg-white p-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Type a message..."
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      // TODO: Send message via converse.js
                      console.log("Send message");
                    }
                  }}
                />
                <button className="rounded-lg border border-blue-600 bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                  Send
                </button>
              </div>
              <div className="mt-2 text-xs text-gray-500">Press Enter to send, Shift+Enter for new line</div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

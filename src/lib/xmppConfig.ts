// XMPP Configuration for Chat
// These values should be set based on your deployment environment

const defaultHost =
  typeof window !== "undefined" ? window.location.hostname : "xps";

export const XMPP_CONFIG = {
  // Prefer env overrides, otherwise default to "same host the browser is on"
  // (important when you open the UI from another laptop on your LAN)
  websocketUrl:
    process.env.NEXT_PUBLIC_XMPP_WEBSOCKET_URL ||
    `ws://${defaultHost}:5280/xmpp-websocket`,
  boshUrl:
    process.env.NEXT_PUBLIC_XMPP_BOSH_URL ||
    `http://${defaultHost}:5280/http-bind`,

  // XMPP domain
  domain: process.env.NEXT_PUBLIC_XMPP_DOMAIN || "automatr-xmpp.local",

  // MUC (Multi-User Chat) domain
  mucDomain:
    process.env.NEXT_PUBLIC_XMPP_MUC_DOMAIN || "conference.automatr-xmpp.local",

  // Default room to auto-join
  defaultRoom: process.env.NEXT_PUBLIC_XMPP_DEFAULT_ROOM || "automatr",

  // ✅ Use WebSocket instead of BOSH (recommended)
  useWebSocket: true,

  // ✅ “just make it work” creds (override via NEXT_PUBLIC_*)
  username: process.env.NEXT_PUBLIC_XMPP_USERNAME || "cli",
  password: process.env.NEXT_PUBLIC_XMPP_PASSWORD || "supersecret",
};

export default XMPP_CONFIG;

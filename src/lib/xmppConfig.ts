// XMPP Configuration for Chat
// These values should be set based on your deployment environment

export const XMPP_CONFIG = {
  // WebSocket or BOSH endpoint
  websocketUrl: process.env.NEXT_PUBLIC_XMPP_WEBSOCKET_URL || "ws://localhost:5280/xmpp-websocket",
  boshUrl: process.env.NEXT_PUBLIC_XMPP_BOSH_URL || "http://localhost:5280/http-bind",

  // XMPP domain
  domain: process.env.NEXT_PUBLIC_XMPP_DOMAIN || "automatr-xmpp.local",

  // MUC (Multi-User Chat) domain
  mucDomain: process.env.NEXT_PUBLIC_XMPP_MUC_DOMAIN || "conference.automatr-xmpp.local",

  // Default room to auto-join (optional)
  defaultRoom: process.env.NEXT_PUBLIC_XMPP_DEFAULT_ROOM || "automatr",

  // Use WebSocket instead of BOSH (recommended)
  useWebSocket: true,
};

export default XMPP_CONFIG;

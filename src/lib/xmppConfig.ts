// src/lib/xmppConfig.ts
// XMPP Configuration for Chat (Converse.js / Headless)
//
// Goal: avoid "host/domain mismatch" by defaulting domain + MUC domain to the same
// hostname the UI was opened with (unless explicitly overridden via NEXT_PUBLIC_*).

type XmppConfig = {
  websocketUrl: string;
  boshUrl: string;
  domain: string;
  mucDomain: string;
  defaultRoom: string;
  useWebSocket: boolean;
  username: string;
  password: string;
};

const defaultHost =
  typeof window !== "undefined" ? window.location.hostname : "xps.local";

const defaultDomain = defaultHost.includes(".") ? defaultHost : `${defaultHost}.local`;

// Optional explicit overrides
const envWs = process.env.NEXT_PUBLIC_XMPP_WEBSOCKET_URL;
const envBosh = process.env.NEXT_PUBLIC_XMPP_BOSH_URL;
const envDomain = process.env.NEXT_PUBLIC_XMPP_DOMAIN;
const envMucDomain = process.env.NEXT_PUBLIC_XMPP_MUC_DOMAIN;

export const XMPP_CONFIG: XmppConfig = {
  // Prefer env overrides, otherwise default to same host as the browser/UI.
  websocketUrl: envWs || `ws://${defaultHost}:5280/xmpp-websocket`,
  boshUrl: envBosh || `http://${defaultHost}:5280/http-bind`,

  // ✅ Fix default mismatch:
  // If you opened the UI at http://xps:3000, default domain becomes "xps"
  // unless NEXT_PUBLIC_XMPP_DOMAIN is explicitly set.
  domain: envDomain || defaultDomain,

  // MUC domain defaults to conference.<domain> (again: no mismatch)
  mucDomain: envMucDomain || `conference.${envDomain || defaultDomain}`,

  // Default room to auto-join
  defaultRoom: process.env.NEXT_PUBLIC_XMPP_DEFAULT_ROOM || "automatr",

  // Use WebSocket by default (recommended)
  useWebSocket: true,

  // “Just make it work” creds (override via NEXT_PUBLIC_*)
  username: process.env.NEXT_PUBLIC_XMPP_USERNAME || "web",
  // Demo/local-only password. Do not use real credentials in browser-exposed config.
  password: "change-me-dev-only",
};

export default XMPP_CONFIG;

// src/lib/xmppServiceUrl.ts
export type XmppTransportUrls = {
  boshUrl: string;
  websocketUrl: string;
  origin: string;
};

/**
 * Derive XMPP transport endpoints from the page origin.
 *
 * This is the key fix for: "site loaded from tail domain, but chat tries xps.local".
 * - If page is https://xps.tail... -> wss://xps.tail.../xmpp-websocket, https://xps.tail.../http-bind
 * - If page is https://xps.local     -> wss://xps.local/xmpp-websocket, https://xps.local/http-bind
 */
export function deriveXmppTransportUrlsFromWindow(): XmppTransportUrls {
  const loc = window.location;
  const httpProto = loc.protocol; // "http:" or "https:"
  const wsProto = httpProto === "https:" ? "wss:" : "ws:";
  const host = loc.host; // includes port if any (e.g. xps.local:3000)

  return {
    origin: loc.origin,
    boshUrl: `${httpProto}//${host}/http-bind`,
    websocketUrl: `${wsProto}//${host}/xmpp-websocket`,
  };
}

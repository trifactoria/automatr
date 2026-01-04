-- /etc/prosody/prosody.cfg.lua
-- Automatr: dev-friendly Prosody config
-- Domain (VirtualHost) MUST match JIDs used by clients: user@DOMAIN

local os = require "os"

local DOMAIN = os.getenv("AUTOMATR_XMPP_DOMAIN") or "xps.local"
local MUC_DOMAIN = "conference." .. DOMAIN

admins = { "andy@" .. DOMAIN, "web@" .. DOMAIN }

modules_enabled = {
  "roster";
  "saslauth";
  "tls";
  "dialback";
  "disco";
  "private";
  "vcard";
  "ping";
  "pep";
  "register";    -- XEP-0077 in-band registration (dev)
  "bosh";        -- /http-bind
  "websocket";   -- /xmpp-websocket
  "http_files";
  "mam";         -- message archive (optional)
  "carbons";     -- message carbons (optional)
  "muc_mam";
--  "smacks";
}

log = {
  info = "*console";
  debug = "*console";
}

-- Allow browser clients to use BOSH from your Next.js origin(s)
http_headers = {
  ["Access-Control-Allow-Origin"] = "*";
  ["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS";
  ["Access-Control-Allow-Headers"] = "Content-Type";
  ["Access-Control-Allow-Credentials"] = "true";
}

-- Allow browser origins (Next.js dev server + LAN)
cross_domain_websocket = {
  "http://xps.local:3000",
  "https://xps.local:3000",
  "http://localhost:3000",
  "https://localhost:3000",
}
cross_domain_websocket = true

cross_domain_bosh = {
  "http://xps.local:3000",
  "https://xps.local:3000",
  "http://localhost:3000",
  "https://localhost:3000",
}
cross_domain_bosh = true

-- dev defaults
allow_registration = true
c2s_require_encryption = false  -- allow non-TLS for dev if needed
s2s_require_encryption = false
consider_websocket_secure = true



-- HTTP for BOSH + WebSocket
http_ports = { 5280 }
https_ports = { 5281 }
http_interfaces = { "*" }

-- Certificates
-- Expecting /etc/prosody/certs/<DOMAIN>.crt + .key (mounted by prosody-up)
ssl = {
  key = "/etc/prosody/certs/" .. DOMAIN .. ".key";
  certificate = "/etc/prosody/certs/" .. DOMAIN .. ".crt";
}

-- Serve this domain
VirtualHost(DOMAIN)

-- MUC component
Component ("conference." .. DOMAIN) "muc"
  name = "Automatr Chat"
  restrict_room_creation = false
  muc_room_locking = false


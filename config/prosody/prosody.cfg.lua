-- config/prosody/prosody.cfg.lua
-- Minimal Prosody config for Automatr: single domain + local MUC
--
-- Goal: make the XMPP VirtualHost configurable via env so that changing ONE variable
-- (AUTOMATR_XMPP_DOMAIN) moves the whole chat stack without editing this file.

local DOMAIN = os.getenv("AUTOMATR_XMPP_DOMAIN") or "automatr-xmpp.local"
local MUC_DOMAIN = "conference." .. DOMAIN

-- Optional: allow overriding the admin username (default: "andy")
local ADMIN_USER = os.getenv("AUTOMATR_XMPP_ADMIN_USER") or "andy"
local ADMIN_JID = ADMIN_USER .. "@" .. DOMAIN

admins = { ADMIN_JID }

log = {
  { levels = { min = "debug" }, to = "console" };
}

-- Core modules needed for auth + MUC + service discovery + HTTP bindings (BOSH/WS)
modules_enabled = {
  -- basics
  "roster";
  "saslauth";
  "tls";
  "dialback";
  "disco";
  "private";
  "vcard";

  -- easy dev UX
  "register";

  -- MUC + useful extras
  "muc";
  "pep";

  -- HTTP server + BOSH + XMPP WebSocket (for Converse)
  "http";
  "bosh";
  "websocket";
}

-- Reasonable defaults for dev
c2s_timeout = 300
s2s_timeout = 300

-- Allow cross-domain BOSH/WS (useful while iterating on UI origins)
cross_domain_bosh = true
cross_domain_websocket = true

-- Dev friendliness
allow_registration = true
allow_unencrypted_plain_auth = true

-- IMPORTANT: keep STARTTLS optional while you debug
c2s_require_encryption = false
s2s_require_encryption = false

-- Listen on standard ports inside container (docker will publish)
c2s_ports = { 5222 }
-- Prosody's HTTP server (BOSH + WS) will be on 5280
http_ports = { 5280 }
http_interfaces = { "*" }

-- Keep it single-host / no external DNS assumptions
use_libevent = true

-- Storage
storage = "internal"

-- Virtual host for the chosen domain
VirtualHost(DOMAIN)
  enabled = true

  -- TLS cert/key location:
  -- Your existing setup uses /var/lib/prosody/<domain>.key/.crt
  -- If you change DOMAIN, you will need matching files there (often easiest in dev:
  -- run bin/prosody-reset to wipe volume, then bring prosody back up).
  ssl = {
    key = "/var/lib/prosody/" .. DOMAIN .. ".key";
    certificate = "/var/lib/prosody/" .. DOMAIN .. ".crt";
  }

-- Local MUC component
Component(MUC_DOMAIN, "muc")
  name = "Automatr MUC"
  restrict_room_creation = false

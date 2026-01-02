-- /etc/prosody/prosody.cfg.lua
-- Minimal Prosody config for Automatr: single domain + local MUC

admins = { "andy@automatr-xmpp.local" }

log = {
  { levels = { min = "debug" }, to = "console" };
}

-- Core modules needed for auth + MUC + service discovery
modules_enabled = {
  "roster";
  "register";
  "saslauth";
  "tls";
  "dialback";
  "disco";
  "pep";
  "ping";
  "smacks";
  "private";
  "websocket";
  "http";
  "bosh";
}

c2s_timeout = 300
s2s_timeout = 300

cross_domain_bosh = true
cross_domain_websocket = true
-- If you want message carbons later: add "carbons" and the xep module.
-- For now keep minimal.

allow_registration = true

-- IMPORTANT: keep STARTTLS optional while you debug
c2s_require_encryption = false
s2s_require_encryption = false

-- Explicit listeners so 5222 is NOT direct TLS.
-- 5222 is plaintext with STARTTLS upgrade.
c2s_ports = { 5222 }
c2s_interfaces = { "*" }

-- Disable legacy direct-TLS port unless you explicitly want it.
-- (If you want it, set legacy_ssl_ports = { 5223 } and configure certs.)
legacy_ssl_ports = { }

s2s_ports = { 5269 }
s2s_interfaces = { "*" }

-- HTTP (optional)
http_ports = { 5280 }
http_interfaces = { "*" }

-- Domain
VirtualHost "automatr-xmpp.local"
  enabled = true

  -- These certs are used for STARTTLS on 5222.
  -- They MUST be a matching key/cert pair and readable by prosody.
  ssl = {
    key = "/var/lib/prosody/automatr-xmpp.local.key";
    certificate = "/var/lib/prosody/automatr-xmpp.local.crt";
  }

-- Local MUC component (NO s2s DNS needed; this is internal)
Component "conference.automatr-xmpp.local" "muc"
  name = "Automatr MUC"

  -- Optional: lock down room creation
  restrict_room_creation = false
  -- If you want Andy to be able to create rooms:
  -- admins = { "andy@automatr-xmpp.local" }

-- Minimal Prosody config for Automatr

admins = { }

modules_enabled = {
    "roster";
    "saslauth";
    "tls";
    "dialback";
    "disco";
}

log = {
  info = "/var/log/prosody/prosody.log";
  error = "/var/log/prosody/prosody.err";
  debug = "/var/log/prosody/prosody.debug";
}

allow_registration = false

c2s_require_encryption = false
s2s_require_encryption = false

VirtualHost "automatr-xmpp.local"
    enabled = true
    ssl = {
        key = "/var/lib/prosody/automatr-xmpp.local.key";
        certificate = "/var/lib/prosody/automatr-xmpp.local.crt";
    }


// src/lib/xmppStropheUtil.ts
export function hasWebCryptoDeriveBits(): boolean {
  try {
    const subtle = globalThis.crypto?.subtle;
    return !!subtle && typeof subtle.deriveBits === "function";
  } catch {
    return false;
  }
}

/**
 * If WebCrypto isn't available (insecure context / older env),
 * Strophe SCRAM can crash. Prune SCRAM SASL mechanisms BEFORE connect().
 */
export function disableScramMechanismsIfNoWebCrypto(Strophe: { SASLMechanisms?: Record<string, unknown> }) {
  if (hasWebCryptoDeriveBits()) return;

  console.warn("[XMPP] crypto.subtle missing; disabling SCRAM SASL mechanisms (forcing PLAIN)");

  try {
    const registry = Strophe.SASLMechanisms;
    if (registry && typeof registry === "object") {
      for (const k of Object.keys(registry)) {
        if (k.toUpperCase().includes("SCRAM")) delete registry[k];
      }
    }
  } catch (e) {
    console.warn("[XMPP] Failed to prune Strophe.SASLMechanisms (ignored)", e);
  }
}

export function nowId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function safeLower(s: string) {
  return (s || "").toLowerCase();
}

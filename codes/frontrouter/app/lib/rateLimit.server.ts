// Per-visitor limits on the routes that spend paid credit (speech recognition, Gemini,
// voice output) or write data. Generous for a real conversation, tight enough that a
// script cannot drain the accounts before the judges arrive. In memory: one frontrouter
// instance, and a restart only forgives.

type Rule = { limit: number; windowMs: number };

export const RULES = {
  // A token opens one listening session, so this is sessions, not sentences.
  sttToken: { limit: 20, windowMs: 10 * 60_000 },
  interpret: { limit: 80, windowMs: 10 * 60_000 },
  speak: { limit: 80, windowMs: 10 * 60_000 },
  contribute: { limit: 120, windowMs: 10 * 60_000 },
  signIn: { limit: 20, windowMs: 10 * 60_000 },
} satisfies Record<string, Rule>;

// Across all visitors: a ceiling on listening sessions per hour, whatever the source.
const GLOBAL_STT = { limit: 400, windowMs: 60 * 60_000 };

const hits = new Map<string, number[]>();

function take(key: string, rule: Rule, now: number): number | null {
  const recent = (hits.get(key) ?? []).filter((t) => now - t < rule.windowMs);
  if (recent.length >= rule.limit) {
    hits.set(key, recent);
    return Math.ceil((rule.windowMs - (now - recent[0])) / 1000);
  }
  recent.push(now);
  hits.set(key, recent);
  return null;
}

// Behind Dokploy's Traefik the visitor's address is the first X-Forwarded-For entry.
export function clientAddress(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return request.headers.get("x-real-ip") ?? "unknown";
}

// Returns a 429 response when the visitor is over the limit, otherwise null.
export function limited(request: Request, name: keyof typeof RULES): Response | null {
  const now = Date.now();
  const retryAfter =
    take(`${name}:${clientAddress(request)}`, RULES[name], now) ??
    (name === "sttToken" ? take("sttToken:all", GLOBAL_STT, now) : null);
  if (retryAfter === null) return null;
  console.warn(`[limit] ${name} refused for ${clientAddress(request)}, retry in ${retryAfter} s`);
  return Response.json(
    { detail: `Too many requests for now. Please try again in ${Math.max(1, Math.round(retryAfter / 60))} min.` },
    { status: 429, headers: { "Retry-After": String(retryAfter) } },
  );
}

// Drop stale entries now and then so the map does not grow with every visitor ever seen.
setInterval(() => {
  const now = Date.now();
  for (const [key, times] of hits) {
    if (times.every((t) => now - t > 60 * 60_000)) hits.delete(key);
  }
}, 10 * 60_000).unref?.();

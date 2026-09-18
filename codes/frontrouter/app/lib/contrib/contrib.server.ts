import { backpyFetch } from "~/lib/backpy.server";

// Calls to backpy's contribution routes. Only this server holds the internal token, and
// it names the user only after reading them from its own signed session cookie.

export type Me = {
  id: string;
  email: string;
  name: string;
  consent: { version: string; accepted_at: string } | null;
  consent_version: string;
  contributions: number;
};

export type ContributionView = {
  id: string;
  created_at: string;
  confirmed_text: string;
  exact: boolean;
  duration_ms: number;
};

export function contributionsConfigured(): boolean {
  return Boolean(process.env.INTERNAL_API_TOKEN);
}

function headers(userId?: string, extra?: HeadersInit): Headers {
  const result = new Headers(extra);
  result.set("X-Internal-Token", process.env.INTERNAL_API_TOKEN ?? "");
  if (userId) result.set("X-User-Id", userId);
  return result;
}

async function json<T>(path: string, init: RequestInit, userId?: string, timeoutMs?: number): Promise<T> {
  const response = await backpyFetch(path, { ...init, headers: headers(userId, init.headers) }, timeoutMs);
  return (await response.json()) as T;
}

export const contrib = {
  sync: (identity: { google_sub: string; email: string; name: string }) =>
    json<Me>("/api/users/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(identity) }),
  me: (userId: string) => json<Me>("/api/me", { method: "GET" }, userId),
  consent: (userId: string, version: string) =>
    json<Me>(
      "/api/me/consent",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version, adult_confirmed: true, agreed: true }) },
      userId,
    ),
  withdraw: (userId: string, deleteContributions: boolean) =>
    json<Me>(
      "/api/me/consent/withdraw",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ delete_contributions: deleteContributions }) },
      userId,
      30_000,
    ),
  deleteAccount: (userId: string) => backpyFetch("/api/me", { method: "DELETE", headers: headers(userId) }, 30_000),
  list: (userId: string) => json<ContributionView[]>("/api/contributions", { method: "GET" }, userId),
  audio: (userId: string, id: string) =>
    backpyFetch(`/api/contributions/${encodeURIComponent(id)}/audio`, { method: "GET", headers: headers(userId) }, 20_000),
  remove: (userId: string, id: string) =>
    backpyFetch(`/api/contributions/${encodeURIComponent(id)}`, { method: "DELETE", headers: headers(userId) }),
  upload: (userId: string, form: FormData) => json<ContributionView>("/api/contributions", { method: "POST", body: form }, userId, 20_000),
};

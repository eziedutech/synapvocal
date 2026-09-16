// Server-only client for backpy. The browser never calls backpy directly:
// in production backpy has no public domain and is reached over the Dokploy internal network.

const TIMEOUT_MS = 5000;

export type BackpyHealth = {
  status: "ok";
  service: "backpy";
  env: string;
  git_sha: string;
  configured: { assemblyai: boolean; deepgram: boolean };
};

export class BackpyError extends Error {}

function baseUrl(): string {
  const url = process.env.BACKPY_INTERNAL_URL;
  if (!url) throw new BackpyError("BACKPY_INTERNAL_URL is not set");
  return url.replace(/\/+$/, "");
}

export async function backpyFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = `${baseUrl()}${path}`;
  let response: Response;
  try {
    response = await fetch(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (cause) {
    console.error(`[backpy] request failed: ${path}`, cause);
    throw new BackpyError(`backpy unreachable at ${path}`, { cause });
  }
  if (!response.ok) {
    console.error(`[backpy] ${path} returned ${response.status}`);
    throw new BackpyError(`backpy ${path} returned ${response.status}`);
  }
  return response;
}

export async function getBackpyHealth(): Promise<BackpyHealth> {
  const response = await backpyFetch("/api/health");
  return (await response.json()) as BackpyHealth;
}

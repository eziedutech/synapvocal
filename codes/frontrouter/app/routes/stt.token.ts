import type { Route } from "./+types/stt.token";
import { limited } from "~/lib/rateLimit.server";
import { backpyFetch, BackpyError } from "~/lib/backpy.server";

// Browser-facing proxy: the browser cannot reach backpy directly.
export async function action({ request }: Route.ActionArgs) {
  if (request.method !== "POST") return Response.json({ detail: "Method not allowed" }, { status: 405 });
  const refused = limited(request, "sttToken");
  if (refused) return refused;
  try {
    // The AssemblyAI token call usually takes 1.5 s but was seen above 5 s; backpy allows 10 s.
    const response = await backpyFetch("/api/stt/token", { method: "POST" }, 12_000);
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const detail = error instanceof BackpyError ? (error.detail ?? error.message) : "Token request failed";
    return Response.json({ detail }, { status: 502 });
  }
}

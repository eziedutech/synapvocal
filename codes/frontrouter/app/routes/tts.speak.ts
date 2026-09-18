import type { Route } from "./+types/tts.speak";
import { limited } from "~/lib/rateLimit.server";
import { backpyFetch, BackpyError } from "~/lib/backpy.server";

// Streams audio from backpy through to the browser without buffering it, so the
// first bytes can play as soon as Deepgram produces them.
const SPEAK_TIMEOUT_MS = 30000;

export async function action({ request }: Route.ActionArgs) {
  if (request.method !== "POST") return Response.json({ detail: "Method not allowed" }, { status: 405 });
  const refused = limited(request, "speak");
  if (refused) return refused;
  const body = await request.text();
  try {
    const upstream = await backpyFetch(
      "/api/tts/speak",
      { method: "POST", headers: { "Content-Type": "application/json" }, body },
      SPEAK_TIMEOUT_MS,
    );
    return new Response(upstream.body, {
      headers: { "Content-Type": "audio/mpeg", "Cache-Control": "no-store" },
    });
  } catch (error) {
    const detail = error instanceof BackpyError ? (error.detail ?? error.message) : "Voice output request failed";
    return Response.json({ detail }, { status: 502 });
  }
}

import type { Route } from "./+types/bridge.interpret";
import { limited } from "~/lib/rateLimit.server";
import { backpyFetch, BackpyError } from "~/lib/backpy.server";

// Browser-facing proxy for interpretation: the browser cannot reach backpy directly.
export async function action({ request }: Route.ActionArgs) {
  if (request.method !== "POST") return Response.json({ detail: "Method not allowed" }, { status: 405 });
  const refused = limited(request, "interpret");
  if (refused) return refused;
  const body = await request.text();
  try {
    // backpy gives Gemini up to three attempts of 12 s each plus short backoff (about 41 s at worst).
    // Giving up sooner turns a slow success into a failure; the heard text stays usable meanwhile.
    const response = await backpyFetch(
      "/api/bridge/interpret",
      { method: "POST", headers: { "Content-Type": "application/json" }, body },
      45_000,
    );
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const detail = error instanceof BackpyError ? (error.detail ?? error.message) : "Interpretation request failed";
    return Response.json({ detail }, { status: 502 });
  }
}

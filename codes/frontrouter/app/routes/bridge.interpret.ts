import type { Route } from "./+types/bridge.interpret";
import { backpyFetch, BackpyError } from "~/lib/backpy.server";

// Browser-facing proxy for interpretation: the browser cannot reach backpy directly.
export async function action({ request }: Route.ActionArgs) {
  if (request.method !== "POST") return Response.json({ detail: "Method not allowed" }, { status: 405 });
  const body = await request.text();
  try {
    const response = await backpyFetch("/api/bridge/interpret", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const detail = error instanceof BackpyError ? (error.detail ?? error.message) : "Interpretation request failed";
    return Response.json({ detail }, { status: 502 });
  }
}

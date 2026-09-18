import type { Route } from "./+types/contribute.audio";
import { contrib } from "~/lib/contrib/contrib.server";
import { getUserId } from "~/lib/session.server";

// A contributor's own recording, so they can hear what they gave. backpy checks that the
// recording belongs to them; anyone else gets 404.
export async function loader({ request, params }: Route.LoaderArgs) {
  const userId = await getUserId(request);
  if (!userId) return new Response("Sign in to listen", { status: 401 });
  try {
    const upstream = await contrib.audio(userId, params.id);
    return new Response(upstream.body, {
      headers: { "Content-Type": "audio/wav", "Cache-Control": "private, no-store" },
    });
  } catch {
    return new Response("Recording not found", { status: 404 });
  }
}

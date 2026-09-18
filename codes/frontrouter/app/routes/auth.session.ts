import type { Route } from "./+types/auth.session";
import { limited } from "~/lib/rateLimit.server";
import { contrib, contributionsConfigured } from "~/lib/contrib/contrib.server";
import { verifyFirebaseToken } from "~/lib/contrib/firebase.server";
import { BackpyError } from "~/lib/backpy.server";
import { sessionConfigured, signIn, signOut } from "~/lib/session.server";

// POST { idToken } signs a contributor in; POST { signOut: true } signs them out.
export async function action({ request }: Route.ActionArgs) {
  if (request.method !== "POST") return Response.json({ detail: "Method not allowed" }, { status: 405 });
  const refused = limited(request, "signIn");
  if (refused) return refused;
  if (!sessionConfigured() || !contributionsConfigured()) {
    return Response.json({ detail: "Contributions are not available on this server" }, { status: 503 });
  }
  const body = (await request.json().catch(() => null)) as { idToken?: string; signOut?: boolean } | null;
  if (body?.signOut) {
    return Response.json({ ok: true }, { headers: { "Set-Cookie": await signOut(request) } });
  }
  if (!body?.idToken) return Response.json({ detail: "Missing sign-in token" }, { status: 400 });

  let identity;
  try {
    identity = await verifyFirebaseToken(body.idToken);
  } catch (error) {
    console.warn("[auth] rejected sign-in token", error instanceof Error ? error.message : error);
    return Response.json({ detail: "Sign-in could not be verified" }, { status: 401 });
  }
  try {
    const me = await contrib.sync({ google_sub: identity.sub, email: identity.email, name: identity.name });
    return Response.json(me, { headers: { "Set-Cookie": await signIn(request, me.id), "Cache-Control": "no-store" } });
  } catch (error) {
    const detail = error instanceof BackpyError ? (error.detail ?? error.message) : "Sign-in failed";
    return Response.json({ detail }, { status: 502 });
  }
}

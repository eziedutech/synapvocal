import type { Route } from "./+types/contribute.upload";
import { limited } from "~/lib/rateLimit.server";
import { BackpyError } from "~/lib/backpy.server";
import { contrib } from "~/lib/contrib/contrib.server";
import { getUserId } from "~/lib/session.server";

// Browser-facing: one confirmed sentence, as WAV plus its details. backpy checks consent
// and the audio format; this route only checks who is asking.
export async function action({ request }: Route.ActionArgs) {
  if (request.method !== "POST") return Response.json({ detail: "Method not allowed" }, { status: 405 });
  const refused = limited(request, "contribute");
  if (refused) return refused;
  const userId = await getUserId(request);
  if (!userId) return Response.json({ detail: "Sign in to contribute" }, { status: 401 });
  const form = await request.formData();
  const audio = form.get("audio");
  const meta = form.get("meta");
  if (!(audio instanceof File) || typeof meta !== "string") {
    return Response.json({ detail: "Recording or details missing" }, { status: 400 });
  }
  const forward = new FormData();
  forward.set("audio", audio, "sentence.wav");
  forward.set("meta", meta);
  try {
    return Response.json(await contrib.upload(userId, forward), { status: 201 });
  } catch (error) {
    const detail = error instanceof BackpyError ? (error.detail ?? error.message) : "Could not save the recording";
    return Response.json({ detail }, { status: 502 });
  }
}

import { getBackpyHealth } from "~/lib/backpy.server";

// Deploy proof: both services report the commit they were built from.
export async function loader() {
  const frontrouter = { service: "frontrouter", git_sha: process.env.GIT_SHA ?? "dev", bundle_sha: __APP_SHA__ };
  try {
    const backpy = await getBackpyHealth();
    return Response.json({ status: "ok", frontrouter, backpy });
  } catch (error) {
    return Response.json(
      { status: "degraded", frontrouter, backpy: null, error: String(error) },
      { status: 503 },
    );
  }
}

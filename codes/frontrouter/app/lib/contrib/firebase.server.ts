import { createRemoteJWKSet, jwtVerify } from "jose";

// Firebase ID tokens are verified with Google's public keys and the project id alone.
// No Firebase admin key is used: signing in needs no admin rights.
const keys = createRemoteJWKSet(
  new URL("https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"),
);

export type FirebasePublicConfig = { apiKey: string; authDomain: string; projectId: string; appId: string };

export function firebasePublicConfig(): FirebasePublicConfig | null {
  const config = {
    apiKey: process.env.FIREBASE_API_KEY ?? "",
    authDomain: process.env.FIREBASE_AUTH_DOMAIN ?? "",
    projectId: process.env.FIREBASE_PROJECT_ID ?? "",
    appId: process.env.FIREBASE_APP_ID ?? "",
  };
  return Object.values(config).every(Boolean) ? config : null;
}

export type GoogleIdentity = { sub: string; email: string; name: string };

export async function verifyFirebaseToken(idToken: string): Promise<GoogleIdentity> {
  const projectId = process.env.FIREBASE_PROJECT_ID;
  if (!projectId) throw new Error("FIREBASE_PROJECT_ID is not set");
  const { payload } = await jwtVerify(idToken, keys, {
    issuer: `https://securetoken.google.com/${projectId}`,
    audience: projectId,
    algorithms: ["RS256"],
  });
  const provider = (payload.firebase as { sign_in_provider?: string } | undefined)?.sign_in_provider;
  if (provider !== "google.com") throw new Error("Only Google sign-in is accepted");
  if (payload.email_verified !== true || typeof payload.email !== "string") throw new Error("Email is not verified");
  if (!payload.sub) throw new Error("Token has no subject");
  return { sub: payload.sub, email: payload.email, name: typeof payload.name === "string" ? payload.name : "" };
}

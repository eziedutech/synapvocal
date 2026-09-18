import { createCookieSessionStorage } from "react-router";

// Signed, httpOnly cookie holding only the backpy user id of a contributor. People who
// never sign in get no cookie at all.
const secret = process.env.SESSION_SECRET;

const storage = createCookieSessionStorage<{ userId: string }>({
  cookie: {
    name: "sv_session",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.APP_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
    secrets: secret ? [secret] : [],
  },
});

export function sessionConfigured(): boolean {
  return Boolean(secret);
}

export async function getUserId(request: Request): Promise<string | null> {
  if (!secret) return null;
  const session = await storage.getSession(request.headers.get("Cookie"));
  return session.get("userId") ?? null;
}

export async function signIn(request: Request, userId: string): Promise<string> {
  const session = await storage.getSession(request.headers.get("Cookie"));
  session.set("userId", userId);
  return storage.commitSession(session);
}

export async function signOut(request: Request): Promise<string> {
  const session = await storage.getSession(request.headers.get("Cookie"));
  return storage.destroySession(session);
}

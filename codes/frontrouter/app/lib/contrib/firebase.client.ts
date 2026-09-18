import type { FirebasePublicConfig } from "./firebase.server";

// Opens Google's sign-in popup through Firebase and returns a Firebase ID token.
// Loaded only when someone presses "Sign in with Google", so the Bridge never downloads it.
// The Firebase session is signed out straight away: from here on only our own cookie counts.
export async function googleIdToken(config: FirebasePublicConfig): Promise<string> {
  const [{ initializeApp, getApps }, { getAuth, GoogleAuthProvider, signInWithPopup, signOut }] = await Promise.all([
    import("firebase/app"),
    import("firebase/auth"),
  ]);
  const app = getApps()[0] ?? initializeApp(config);
  const auth = getAuth(app);
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  const result = await signInWithPopup(auth, provider);
  const token = await result.user.getIdToken();
  await signOut(auth);
  return token;
}

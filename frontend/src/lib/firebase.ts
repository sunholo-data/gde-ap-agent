import { type FirebaseApp, getApps, initializeApp } from "firebase/app";
import {
  type Auth,
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut as fbSignOut,
  type User,
} from "firebase/auth";
import { type Firestore, getFirestore } from "firebase/firestore";
import {
  isAnonymousGroupAuthMode,
  readStoredGroupSession,
} from "@/lib/anonymousGroupAuth";
import { isLocalMode, LOCAL_MODE_STUB_TOKEN } from "@/lib/localMode";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

let appInstance: FirebaseApp | null = null;
let authInstance: Auth | null = null;

function isConfigured(): boolean {
  return Boolean(firebaseConfig.apiKey && firebaseConfig.projectId);
}

export function getFirebaseApp(): FirebaseApp | null {
  // LOCAL_MODE: no Firebase init at all — LocalAuthProvider supplies a
  // deterministic identity. Returning null keeps existing `if (!app)`
  // branches working without further changes.
  if (isLocalMode()) return null;
  if (!isConfigured()) return null;
  if (appInstance) return appInstance;
  appInstance = getApps()[0] ?? initializeApp(firebaseConfig);
  return appInstance;
}

export function getFirebaseAuth(): Auth | null {
  if (authInstance) return authInstance;
  const app = getFirebaseApp();
  if (!app) return null;
  authInstance = getAuth(app);
  return authInstance;
}

export function subscribeToAuthState(
  callback: (user: User | null) => void,
): () => void {
  const auth = getFirebaseAuth();
  if (!auth) {
    // Not configured (e.g. build time or missing env). Report signed-out.
    callback(null);
    return () => {};
  }
  return onAuthStateChanged(auth, callback);
}

export async function getIdToken(): Promise<string | null> {
  // Anonymous group-ID mode (sprint 2.11): token lives in sessionStorage,
  // written by AnonymousGroupAuthProvider. Checked BEFORE LOCAL_MODE
  // because the group-auth env var explicitly overrides LOCAL_MODE
  // when forks want to demo without standing up Firebase.
  if (isAnonymousGroupAuthMode()) {
    const session = readStoredGroupSession();
    return session?.token ?? null;
  }
  // LOCAL_MODE: every request sends the well-known stub token so the
  // backend's auth/local_mode_stub.py grants it. fetchWithAuth wires this
  // into the Authorization header on every /api/proxy/* request.
  if (isLocalMode()) return LOCAL_MODE_STUB_TOKEN;
  const auth = getFirebaseAuth();
  if (!auth?.currentUser) return null;
  return auth.currentUser.getIdToken();
}

/**
 * Sign in with Google. Prefers a popup; on Safari (which blocks third-party
 * storage the popup flow relies on unless the user clicks very recently), the
 * caller can fall back to `signInWithGoogleRedirect`. We do NOT try to detect
 * Safari automatically — popup failure is caught by the caller and re-tried
 * via redirect on that code path.
 */
export async function signInWithGoogle(): Promise<void> {
  const auth = getFirebaseAuth();
  if (!auth) throw new Error("firebase not configured");
  const provider = new GoogleAuthProvider();
  await signInWithPopup(auth, provider);
}

export async function signInWithGoogleRedirect(): Promise<void> {
  const auth = getFirebaseAuth();
  if (!auth) throw new Error("firebase not configured");
  const provider = new GoogleAuthProvider();
  await signInWithRedirect(auth, provider);
}

export async function signOut(): Promise<void> {
  const auth = getFirebaseAuth();
  if (!auth) return;
  await fbSignOut(auth);
}

export function getFirestoreDb(): Firestore | null {
  const app = getFirebaseApp();
  if (!app) return null;
  return getFirestore(app);
}

export function firestoreTimestampToIso(value: unknown): string | null {
  if (!value) return null;
  if (typeof value === "string") return value;
  if (typeof value === "object" && value !== null && "toDate" in value) {
    const d = (value as { toDate: () => Date }).toDate?.();
    return d instanceof Date ? d.toISOString() : null;
  }
  return null;
}

export type { User };

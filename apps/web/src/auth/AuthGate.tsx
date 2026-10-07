import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { onAuthStateChanged, signInWithEmailAndPassword, signOut, type User } from "firebase/auth";
import { useQueryClient } from "@tanstack/react-query";

import { firebaseAuth } from "./firebase";

export function AuthGate({ children }: { children: ReactNode }) {
  const auth = firebaseAuth;
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(firebaseAuth));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!auth) return;
    let observedInitialState = false;
    let previousUid: string | null = null;
    return onAuthStateChanged(auth, (currentUser) => {
      const currentUid = currentUser?.uid ?? null;
      if (observedInitialState && previousUid !== currentUid) {
        queryClient.clear();
        try {
          window.sessionStorage.clear();
        } catch {
          // Storage can be disabled by browser policy.
        }
      }
      observedInitialState = true;
      previousUid = currentUid;
      setUser(currentUser);
      setLoading(false);
    });
  }, [auth, queryClient]);

  if (!auth) return children;
  if (loading) return <main className="sign-in-page">Checking sign-in status…</main>;

  if (user) {
    return (
      <>
        <div className="account-session">
          <span>Signed in</span>
          <button type="button" onClick={() => void signOut(auth)}>
            Sign out
          </button>
        </div>
        {children}
      </>
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!auth) return;
    setSubmitting(true);
    setError("");
    try {
      await signInWithEmailAndPassword(auth, email.trim(), password);
      setPassword("");
    } catch {
      setError("Sign-in failed. Check the account details and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="sign-in-page">
      <form className="sign-in-card" onSubmit={submit}>
        <h1>Shopping Assistant</h1>
        <p>Sign in with the account configured for this deployment.</p>
        <label>
          Email
          <input
            autoComplete="username"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            autoComplete="current-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

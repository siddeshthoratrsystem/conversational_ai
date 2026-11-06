// Who is signed in, and every way that changes (spec 009, data-model.md "State: web sign-in").
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { configureApi } from "@convai/core";
import { getAuthClient } from "./client";
import { IdleWarning } from "./IdleWarning";
import { clearResume, saveResume, type Resume } from "./resume";
import { useIdleTimeout } from "./useIdleTimeout";
import { userFromName, type User } from "./user";

export type SignedOutReason = "failed" | "unreachable" | "timed-out" | "session-ended";

export type AuthState =
  | { status: "starting" }
  | { status: "signed-out"; reason?: SignedOutReason }
  | { status: "signed-in"; user: User };

type AuthContextValue = {
  state: AuthState;
  signIn(): void;
  retry(): void;
  signOut(): void;
  endSession(reason: "timed-out" | "session-ended"): void;
  /** The chat registers how to read its open chat and draft, saved if the session ends (FR-009). */
  setResumeSource(source: (() => Resume) | null): void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

const CALLBACK_PATH = "/auth/callback";

function signedInState(name: string | null): AuthState {
  return { status: "signed-in", user: userFromName(name ?? "there") };
}

function initialState(): AuthState {
  localStorage.removeItem("convai.user"); // spec 008's demo sign-in kept a token here (FR-003)
  const client = getAuthClient();
  // Already holding a token (e.g. a host app or test handed one over): no need to wait.
  if (client.getAccessToken() && window.location.pathname !== CALLBACK_PATH) {
    return signedInState(client.getUserName());
  }
  return { status: "starting" };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(initialState);
  const started = useRef(false); // StrictMode runs effects twice; sign in only once
  const resumeSource = useRef<(() => Resume) | null>(null);

  // Lost session (timeout, failed renewal): keep where they were, clear the screen and tokens.
  const endSession = useCallback((reason: "timed-out" | "session-ended") => {
    const resume = resumeSource.current?.();
    if (resume) saveResume(resume);
    void getAuthClient().forget();
    setState({ status: "signed-out", reason });
  }, []);

  useEffect(() => getAuthClient().onRenewFailed(() => endSession("session-ended")), [endSession]);

  const checkSilently = useCallback(async () => {
    const client = getAuthClient();
    try {
      const ok = await client.signInSilent();
      setState(ok ? signedInState(client.getUserName()) : { status: "signed-out" });
    } catch {
      setState({ status: "signed-out", reason: "unreachable" });
    }
  }, []);

  // Start: finish a redirect sign-in, or look for an existing session.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (state.status === "signed-in") return;
    const client = getAuthClient();
    if (window.location.pathname === CALLBACK_PATH) {
      client
        .handleCallback()
        .then(() => setState(signedInState(client.getUserName())))
        .catch(() => setState({ status: "signed-out", reason: "failed" }))
        .finally(() => window.history.replaceState(null, "", "/"));
    } else {
      void checkSilently();
    }
  }, [state.status, checkSilently]);

  // Every API call carries the token; a 401 renews once, then ends the session (research R9).
  // Set during the first render, because the chat's own effects run (and call the API) before ours.
  const apiConfigured = useRef(false);
  // No cleanup: StrictMode's test unmount would clear it without a new render to set it again.
  if (!apiConfigured.current) {
    apiConfigured.current = true;
    const client = getAuthClient();
    configureApi({
      getToken: () => client.getAccessToken(),
      onUnauthorized: async () => {
        if (await client.renew()) return true;
        endSession("session-ended");
        return false;
      },
    });
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      endSession,
      signIn: () => void getAuthClient().signInRedirect(),
      retry: () => {
        if (state.status === "signed-out" && state.reason === "unreachable") {
          setState({ status: "starting" });
          void checkSilently();
        } else {
          void getAuthClient().signInRedirect();
        }
      },
      signOut: () => {
        clearResume(); // a deliberate sign-out forgets the chat and draft
        setState({ status: "signed-out" });
        void getAuthClient().signOut();
      },
      setResumeSource: (source) => {
        resumeSource.current = source;
      },
    }),
    [state, endSession, checkSilently],
  );

  const idle = useIdleTimeout(state.status === "signed-in", () => endSession("timed-out"));

  return (
    <AuthContext.Provider value={value}>
      {children}
      {idle.secondsLeft !== null && state.status === "signed-in" && (
        <IdleWarning secondsLeft={idle.secondsLeft} onStay={idle.stay} onSignOut={value.signOut} />
      )}
    </AuthContext.Provider>
  );
}

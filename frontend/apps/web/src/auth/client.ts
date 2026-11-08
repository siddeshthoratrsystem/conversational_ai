// The sign-in seam (spec 009). AuthProvider only talks to this interface, so tests use a fake
// and the OIDC library stays in one file (oidc.ts). A host app that embeds the chat can skip all
// of this and hand its own token to configureApi({ getToken }) (FR-017).
import { createOidcClient } from "./oidc";

export interface AuthClient {
  /** Sign in without showing anything (provider session cookie). Returns false if there is no
   * session; throws if the sign-in service can't be reached. */
  signInSilent(): Promise<boolean>;
  /** Go to the sign-in page. */
  signInRedirect(): Promise<void>;
  /** Finish a sign-in on the /auth/callback page. Throws if it failed or was cancelled. */
  handleCallback(): Promise<void>;
  /** Renew the token now. Returns false if that failed. */
  renew(): Promise<boolean>;
  /** Forget the tokens here and end the session at the sign-in service. */
  signOut(): Promise<void>;
  /** Lost session (idle timeout, failed renewal): forget the tokens and end the provider session
   * without leaving the page. */
  forget(): Promise<void>;
  /** Current access token, or null. */
  getAccessToken(): string | null;
  /** The signed-in customer's display name from the sign-in token, or null (FR-006). */
  getUserName(): string | null;
  /** Called when background renewal fails. Returns an unsubscribe function. */
  onRenewFailed(cb: () => void): () => void;
}

let client: AuthClient | null = null;

/** The app's sign-in client: the OIDC one unless a test installed another. */
export function getAuthClient(): AuthClient {
  if (!client) client = createOidcClient();
  return client;
}

/** Tests: install a fake (or null to go back to the default). */
export function setAuthClient(next: AuthClient | null): void {
  client = next;
}

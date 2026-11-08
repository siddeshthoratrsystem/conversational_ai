// OIDC sign-in with oidc-client-ts (spec 009, research R2–R3). Settings come from the
// VITE_OIDC_* variables, so moving from the local Keycloak to Okta needs no code change.
import {
  ErrorResponse,
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
  type User,
  type UserManagerSettings,
} from "oidc-client-ts";

import type { AuthClient } from "./client";

// Answers meaning "nobody is signed in at the provider", as opposed to "the provider is down".
const NO_SESSION = new Set(["login_required", "interaction_required", "consent_required", "account_selection_required"]);

export function oidcSettings(): UserManagerSettings {
  const env = import.meta.env;
  const origin = window.location.origin;
  return {
    authority: env.VITE_OIDC_AUTHORITY || "http://localhost:8081/realms/convai",
    client_id: env.VITE_OIDC_CLIENT_ID || "convai-web",
    scope: env.VITE_OIDC_SCOPE || "openid profile",
    redirect_uri: `${origin}/auth/callback`,
    silent_redirect_uri: `${origin}/silent-callback.html`,
    post_logout_redirect_uri: `${origin}/`,
    response_type: "code",
    // Tokens stay in memory only (FR-003); the PKCE state for the redirect uses sessionStorage.
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    automaticSilentRenew: true,
    accessTokenExpiringNotificationTimeInSeconds: 30, // renew 30 s before expiry
    silentRequestTimeoutInSeconds: 5,
  };
}

export function createOidcClient(): AuthClient {
  const manager = new UserManager(oidcSettings());
  let accessToken: string | null = null;
  let userName: string | null = null;

  const remember = (user: User | null) => {
    accessToken = user?.access_token ?? null;
    userName = user ? (user.profile.name ?? user.profile.preferred_username ?? user.profile.sub) : null;
  };
  manager.events.addUserLoaded(remember);
  manager.events.addUserUnloaded(() => remember(null));

  return {
    async signInSilent() {
      try {
        remember(await manager.signinSilent());
        return accessToken !== null;
      } catch (e) {
        if (e instanceof ErrorResponse && e.error && NO_SESSION.has(e.error)) return false;
        throw e;
      }
    },
    signInRedirect: () => manager.signinRedirect(),
    async handleCallback() {
      remember(await manager.signinRedirectCallback());
    },
    async renew() {
      try {
        remember(await manager.signinSilent());
        return accessToken !== null;
      } catch {
        return false;
      }
    },
    async signOut() {
      const user = await manager.getUser();
      remember(null);
      await manager.removeUser();
      await manager.signoutRedirect({ id_token_hint: user?.id_token });
    },
    async forget() {
      // A lost session (idle timeout, failed renewal) also ends the provider session, in a hidden
      // frame, so signing in again needs the password (spec 009 FR-008 on shared devices).
      const user = await manager.getUser();
      remember(null);
      await manager.removeUser();
      if (user?.id_token) await manager.signoutSilent({ id_token_hint: user.id_token }).catch(() => undefined);
    },
    getAccessToken: () => accessToken,
    getUserName: () => userName,
    onRenewFailed(cb) {
      return manager.events.addSilentRenewError(cb);
    },
  };
}

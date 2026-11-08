// A fake sign-in client for tests (spec 009). No network, no OIDC library.
import { setAuthClient, type AuthClient } from "@/auth/client";

export type FakeAuth = AuthClient & {
  /** Whether the provider "has a session" for signInSilent. */
  providerSession: boolean;
  /** Make signInSilent throw, as if the sign-in service were down. */
  unreachable: boolean;
  /** Make handleCallback throw (sign-in failed or cancelled). */
  callbackFails: boolean;
  /** Result of the next renew() calls. */
  renewSucceeds: boolean;
  token: string | null;
  /** Display name in the "sign-in token". */
  name: string;
  calls: string[];
  /** Fire the background-renewal failure event. */
  failRenewal(): void;
};

export function installFakeAuth(
  options: Partial<Pick<FakeAuth, "providerSession" | "unreachable" | "token" | "name">> = {},
): FakeAuth {
  const listeners = new Set<() => void>();
  let tokenCount = 0;
  const nextToken = () => `token-${++tokenCount}`;

  const fake: FakeAuth = {
    providerSession: options.providerSession ?? false,
    unreachable: options.unreachable ?? false,
    callbackFails: false,
    renewSucceeds: true,
    token: options.token ?? null,
    name: options.name ?? "Vinod",
    calls: [],
    async signInSilent() {
      fake.calls.push("signInSilent");
      if (fake.unreachable) throw new Error("network");
      if (!fake.providerSession) return false;
      fake.token = nextToken();
      return true;
    },
    async signInRedirect() {
      fake.calls.push("signInRedirect");
    },
    async handleCallback() {
      fake.calls.push("handleCallback");
      if (fake.callbackFails) throw new Error("access_denied");
      fake.providerSession = true;
      fake.token = nextToken();
    },
    async renew() {
      fake.calls.push("renew");
      if (!fake.renewSucceeds) {
        fake.token = null;
        return false;
      }
      fake.token = nextToken();
      return true;
    },
    async signOut() {
      fake.calls.push("signOut");
      fake.token = null;
      fake.providerSession = false;
    },
    async forget() {
      fake.calls.push("forget");
      fake.token = null;
    },
    getAccessToken: () => fake.token,
    getUserName: () => (fake.token ? fake.name : null),
    onRenewFailed(cb) {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    failRenewal() {
      fake.token = null;
      listeners.forEach((cb) => cb());
    },
  };

  setAuthClient(fake);
  return fake;
}

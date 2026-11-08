import { Button } from "@convai/ui/button";
import { Card } from "@convai/ui/card";
import { PrincipalLogo } from "@convai/ui/logo";

import type { SignedOutReason } from "./AuthProvider";

function idleMinutes(): number {
  const n = Number(import.meta.env.VITE_IDLE_TIMEOUT_MINUTES);
  return Number.isFinite(n) && n > 0 ? n : 15;
}

/** Sign-in prompt in the Principal style (spec 009). Sign-in itself happens at the sign-in service. */
export function LoginPage({
  reason,
  onSignIn,
  onRetry,
}: {
  reason?: SignedOutReason;
  onSignIn: () => void;
  onRetry: () => void;
}) {
  const error =
    reason === "failed"
      ? "Sign-in didn't complete."
      : reason === "unreachable"
        ? "We can't reach the sign-in service right now."
        : null;
  const info =
    reason === "timed-out"
      ? `You were signed out after ${idleMinutes()} minutes of inactivity.`
      : reason === "session-ended"
        ? "Your session has ended. Sign in to continue."
        : null;

  return (
    <div className="relative flex min-h-full flex-col items-center overflow-hidden bg-page px-6 py-16">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-125 left-1/2 h-185.75 w-321.5 -translate-x-1/2 bg-aura opacity-30"
      />
      <main className="relative flex w-full max-w-110 flex-col items-center gap-8 pt-[6vh]">
        <PrincipalLogo />
        <Card variant="tile" className="flex w-full flex-col gap-6 p-8">
          <header className="flex flex-col gap-1">
            <h1 className="text-2xl font-bold text-navy">Sign in to Alfred</h1>
            <p className="text-base text-muted">Your AI guide to your Principal plan.</p>
          </header>
          {info && (
            <p role="status" className="rounded-md bg-info-50 px-4 py-3 text-sm text-navy">
              {info}
            </p>
          )}
          {error ? (
            <div role="alert" className="flex flex-col gap-3 rounded-md border border-danger-500 bg-white px-4 py-3 text-sm text-danger-500">
              <p>{error}</p>
              <Button variant="secondary" className="self-start" onClick={onRetry}>
                Try again
              </Button>
            </div>
          ) : (
            <Button variant="primary" className="w-full" onClick={onSignIn}>
              Sign in
            </Button>
          )}
        </Card>
      </main>
    </div>
  );
}

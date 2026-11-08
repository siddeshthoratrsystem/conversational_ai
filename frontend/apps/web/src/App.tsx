import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { LoginPage } from "@/auth/LoginPage";
import { ChatApp } from "@/chat/ChatApp";

/** Signs the customer in (spec 009), then shows the Alfred chat. */
export default function App() {
  return (
    <AuthProvider>
      <Screens />
    </AuthProvider>
  );
}

function Screens() {
  const { state, signIn, retry, signOut } = useAuth();

  if (state.status === "starting") {
    return (
      <p role="status" className="flex min-h-full items-center justify-center bg-page text-muted">
        Signing in…
      </p>
    );
  }
  if (state.status === "signed-out") return <LoginPage reason={state.reason} onSignIn={signIn} onRetry={retry} />;
  return <ChatApp user={state.user} onSignOut={signOut} />;
}

/// <reference types="vite/client" />

// Web settings (spec 009); see apps/web/.env.example.
interface ImportMetaEnv {
  readonly VITE_OIDC_AUTHORITY?: string;
  readonly VITE_OIDC_CLIENT_ID?: string;
  readonly VITE_OIDC_SCOPE?: string;
  readonly VITE_IDLE_TIMEOUT_MINUTES?: string;
  readonly VITE_IDLE_WARNING_MINUTES?: string;
}

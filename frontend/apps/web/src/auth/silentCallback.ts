// Runs inside the hidden frame and hands the result back to the app (spec 009): a silent sign-in
// or renewal answer has a code or error; a silent sign-out answer has neither.
import { UserManager } from "oidc-client-ts";

import { oidcSettings } from "./oidc";

const manager = new UserManager(oidcSettings());
const params = new URLSearchParams(window.location.search);
void (params.has("code") || params.has("error") ? manager.signinSilentCallback() : manager.signoutSilentCallback());

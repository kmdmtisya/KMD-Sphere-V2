import "server-only";

import * as client from "openid-client";

import { isLoopback, type AuthSettings } from "./settings";
import type { SessionUser, TokenSet } from "./session";

/**
 * The BFF's OIDC client (openid-client, ADR-0018): a confidential client using the Authorization
 * Code flow with PKCE (S256), state and nonce. Discovery is cached per process.
 */
let configuration: Promise<client.Configuration> | null = null;

export function oidcConfiguration(settings: AuthSettings): Promise<client.Configuration> {
  configuration ??= client
    .discovery(settings.issuer, settings.clientId, undefined, client.ClientSecretBasic(settings.clientSecret), {
      // Plain http is accepted only for a loopback issuer (local stack and CI); see authSettings.
      execute: isLoopback(settings.issuer) && settings.issuer.protocol === "http:" ? [client.allowInsecureRequests] : [],
    })
    .catch((error: unknown) => {
      configuration = null;
      throw error;
    });
  return configuration;
}

export function callbackUrl(settings: AuthSettings): URL {
  return new URL("/api/auth/callback", settings.publicUrl);
}

export type SignInTransaction = { state: string; nonce: string; verifier: string; returnTo: string; startedAt: number };

export async function startSignIn(settings: AuthSettings, returnTo: string): Promise<{ url: URL; transaction: SignInTransaction }> {
  const config = await oidcConfiguration(settings);
  const verifier = client.randomPKCECodeVerifier();
  const transaction: SignInTransaction = {
    state: client.randomState(),
    nonce: client.randomNonce(),
    verifier,
    returnTo,
    startedAt: Date.now(),
  };
  const url = client.buildAuthorizationUrl(config, {
    redirect_uri: callbackUrl(settings).href,
    scope: "openid profile email",
    code_challenge: await client.calculatePKCECodeChallenge(verifier),
    code_challenge_method: "S256",
    state: transaction.state,
    nonce: transaction.nonce,
  });
  return { url, transaction };
}

function tokenSet(tokens: client.TokenEndpointResponse): TokenSet {
  return {
    accessToken: tokens.access_token,
    expiresIn: tokens.expires_in ?? 60,
    refreshToken: tokens.refresh_token,
    idToken: tokens.id_token,
  };
}

/** Exchanges the authorization code; verifies state, nonce, PKCE and the ID token. */
export async function finishSignIn(
  settings: AuthSettings,
  currentUrl: URL,
  transaction: SignInTransaction,
): Promise<{ user: SessionUser; tokens: TokenSet }> {
  const config = await oidcConfiguration(settings);
  const tokens = await client.authorizationCodeGrant(config, currentUrl, {
    pkceCodeVerifier: transaction.verifier,
    expectedState: transaction.state,
    expectedNonce: transaction.nonce,
    idTokenExpected: true,
  });
  const claims = tokens.claims();
  if (!claims) throw new Error("no ID token claims");
  const user: SessionUser = {
    sub: claims.sub,
    name: typeof claims.name === "string" ? claims.name : undefined,
    email: typeof claims.email === "string" ? claims.email : undefined,
  };
  return { user, tokens: tokenSet(tokens) };
}

export async function refreshTokens(settings: AuthSettings, refreshToken: string): Promise<TokenSet> {
  return tokenSet(await client.refreshTokenGrant(await oidcConfiguration(settings), refreshToken));
}

/** Best-effort revocation of the refresh token at sign-out; the Keycloak session also ends via logout. */
export async function revokeRefreshToken(settings: AuthSettings, refreshToken: string): Promise<void> {
  try {
    await client.tokenRevocation(await oidcConfiguration(settings), refreshToken, { token_type_hint: "refresh_token" });
  } catch {
    // The session is already gone on our side; RP-initiated logout ends the SSO session.
  }
}

export async function endSessionUrl(settings: AuthSettings, idToken: string | undefined): Promise<URL> {
  const config = await oidcConfiguration(settings);
  return client.buildEndSessionUrl(config, {
    post_logout_redirect_uri: new URL("/", settings.publicUrl).href,
    ...(idToken ? { id_token_hint: idToken } : { client_id: settings.clientId }),
  });
}

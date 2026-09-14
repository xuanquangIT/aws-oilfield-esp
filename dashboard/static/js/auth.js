/* Hosted Cognito authorization-code + PKCE flow. Local fixture mode stays anonymous. */
(function () {
  "use strict";
  const KEY = "esp_dashboard_auth";
  const encoder = new TextEncoder();

  function base64Url(bytes) {
    return btoa(String.fromCharCode(...new Uint8Array(bytes)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  async function digest(value) { return base64Url(await crypto.subtle.digest("SHA-256", encoder.encode(value))); }
  function random() { return base64Url(crypto.getRandomValues(new Uint8Array(32))); }
  function stored() { try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (_) { return null; } }
  function save(value) { sessionStorage.setItem(KEY, JSON.stringify(value)); }

  async function config() {
    const response = await fetch("/api/v1/config", { headers: { Accept: "application/json" } });
    if (!response.ok) return null;
    const data = await response.json();
    return data && data.auth && data.auth.domain && data.auth.client_id ? data.auth : null;
  }
  async function redirectToLogin(auth) {
    const verifier = random(), state = random();
    sessionStorage.setItem("esp_dashboard_pkce", JSON.stringify({ verifier, state }));
    const params = new URLSearchParams({ response_type: "code", client_id: auth.client_id, redirect_uri: location.origin + "/", scope: "openid email", state, code_challenge: await digest(verifier), code_challenge_method: "S256" });
    location.replace(auth.domain + "/login?" + params.toString());
  }
  async function redeem(auth, code, state) {
    const pending = JSON.parse(sessionStorage.getItem("esp_dashboard_pkce") || "null");
    if (!pending || pending.state !== state) throw new Error("Invalid sign-in response");
    const body = new URLSearchParams({ grant_type: "authorization_code", client_id: auth.client_id, code, redirect_uri: location.origin + "/", code_verifier: pending.verifier });
    const response = await fetch(auth.domain + "/oauth2/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
    if (!response.ok) throw new Error("Unable to complete sign-in");
    const token = await response.json();
    if (!token.id_token) throw new Error("Missing identity token");
    save({ id_token: token.id_token, expires_at: Date.now() + Math.max(60, Number(token.expires_in || 300) - 30) * 1000 });
    sessionStorage.removeItem("esp_dashboard_pkce");
    history.replaceState({}, document.title, location.pathname);
  }
  window.dashboardAuth = {
    async initialize() {
      const auth = await config().catch(() => null);
      if (!auth) return; // Local fixture/loopback server intentionally has no hosted auth endpoint.
      const params = new URLSearchParams(location.search);
      if (params.get("code")) await redeem(auth, params.get("code"), params.get("state"));
      const token = stored();
      if (!token || !token.id_token || token.expires_at <= Date.now()) await redirectToLogin(auth);
    },
    header() { const token = stored(); return token && token.expires_at > Date.now() ? { Authorization: "Bearer " + token.id_token } : {}; },
    async unauthorized() { sessionStorage.removeItem(KEY); const auth = await config().catch(() => null); if (auth) await redirectToLogin(auth); }
  };
})();

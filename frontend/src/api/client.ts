import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";
import { PROBLEM, problemType } from "./problem";

const CSRF_COOKIE = "kapataz_csrf";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function readCookie(name: string, source: string = document.cookie): string | undefined {
  for (const part of source.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return undefined;
}

async function fetchCsrf(): Promise<string | undefined> {
  await fetch("/api/auth/csrf", { credentials: "same-origin" });
  return readCookie(CSRF_COOKIE);
}

// El token CSRF va firmado por el servidor: la SPA solo copia la cookie en la cabecera.
// Si la cookie aún no existe, se pide antes con GET /api/auth/csrf.
const originals = new WeakMap<Request, Request>();
const retried = new WeakSet<Request>();

const csrf: Middleware = {
  async onRequest({ request }) {
    if (SAFE_METHODS.has(request.method)) return undefined;
    const token = readCookie(CSRF_COOKIE) ?? (await fetchCsrf());
    if (token) request.headers.set("X-CSRF-Token", token);
    originals.set(request, request.clone());
    return request;
  },
  // Si el servidor rechaza el token (csrf-no-valido), se renueva y se reintenta una sola vez.
  async onResponse({ request, response }) {
    const original = originals.get(request);
    originals.delete(request);
    if (!original || retried.has(request) || response.status !== 403) return undefined;
    const body: unknown = await response
      .clone()
      .json()
      .catch(() => null);
    if (problemType(body) !== PROBLEM.csrfInvalid) return undefined;
    const token = await fetchCsrf();
    if (!token) return undefined;
    const retry = new Request(original);
    retried.add(retry);
    retry.headers.set("X-CSRF-Token", token);
    return fetch(retry);
  },
};

export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  credentials: "same-origin",
});
api.use(csrf);

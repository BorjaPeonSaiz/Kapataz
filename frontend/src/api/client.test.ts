import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

const problem = (type: string, status: number) =>
  new Response(JSON.stringify({ type }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });

describe("cliente de API: CSRF", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = "kapataz_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("copia la cookie en X-CSRF-Token y reintenta una sola vez si es csrf-no-valido req('RF-AC-01') owasp('A01')", async () => {
    document.cookie = "kapataz_csrf=viejo";
    const seen: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.endsWith("/api/auth/csrf")) {
        document.cookie = "kapataz_csrf=nuevo";
        return new Response(null, { status: 204 });
      }
      seen.push((input as Request).headers.get("X-CSRF-Token") ?? "");
      return seen.length === 1
        ? problem("/problemas/csrf-no-valido", 403)
        : new Response(null, { status: 204 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { response } = await api.POST("/api/auth/logout", {
      fetch: (r: Request) => fetchMock(r),
    });
    expect(seen).toEqual(["viejo", "nuevo"]);
    expect(response.status).toBe(204);
  });
});

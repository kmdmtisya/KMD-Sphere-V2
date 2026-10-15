import { afterEach, describe, expect, it, vi } from "vitest";

import { GET as health } from "./health/route";
import { DELETE, GET, POST } from "./proxy/[...path]/route";

const ctx = (path?: string[]) => ({ params: Promise.resolve({ path }) });

afterEach(() => vi.restoreAllMocks());

describe("BFF proxy skeleton", () => {
  it("answers 401 for allowed paths: nobody is signed in until P14-T05, so nothing is forwarded", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const response = await GET(new Request("http://web.test/api/proxy/portfolios"), ctx(["portfolios"]));
    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({ detail: "Not signed in" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("answers 404 for paths outside the allow-list", async () => {
    const post = await POST(new Request("http://web.test/api/proxy/x", { method: "POST" }), ctx(["..", "x"]));
    expect(post.status).toBe(404);
    const del = await DELETE(new Request("http://web.test/api/proxy", { method: "DELETE" }), ctx(undefined));
    expect(del.status).toBe(404);
  });
});

describe("health", () => {
  it("reports the API as ok when its liveness probe answers", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    const response = await health();
    expect(await response.json()).toEqual({ web: "ok", api: "ok" });
    expect(String(fetchSpy.mock.calls[0][0])).toBe("http://127.0.0.1:8000/health/live");
  });

  it("reports the API as unavailable when it cannot be reached", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const response = await health();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ web: "ok", api: "unavailable" });
  });
});

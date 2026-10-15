import { describe, expect, it } from "vitest";

import { serverConfig } from "./config";

describe("serverConfig", () => {
  it("defaults to the local API", () => {
    expect(serverConfig({}).apiBaseUrl.href).toBe("http://127.0.0.1:8000/");
  });

  it("accepts https and loopback http", () => {
    expect(serverConfig({ WS_API_BASE_URL: "https://api.example.test" }).apiBaseUrl.host).toBe("api.example.test");
    expect(serverConfig({ WS_API_BASE_URL: "http://localhost:8765" }).apiBaseUrl.port).toBe("8765");
  });

  it("refuses plain http to other hosts, credentials and invalid URLs", () => {
    expect(() => serverConfig({ WS_API_BASE_URL: "http://api.example.test" })).toThrow(/https/);
    expect(() => serverConfig({ WS_API_BASE_URL: "https://user:pass@api.example.test" })).toThrow(/credentials/);
    expect(() => serverConfig({ WS_API_BASE_URL: "not a url" })).toThrow(/valid URL/);
  });
});

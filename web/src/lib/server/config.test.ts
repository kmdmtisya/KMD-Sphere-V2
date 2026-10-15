import { describe, expect, it } from "vitest";

import { serverConfig } from "./config";

describe("serverConfig", () => {
  it("defaults to the local API", () => {
    expect(serverConfig({}).apiBaseUrl.href).toBe("http://127.0.0.1:8000/");
  });

  it("accepts https and loopback http", () => {
    expect(
      serverConfig({ WS_API_BASE_URL: "https://api.example.test" }).apiBaseUrl
        .host,
    ).toBe("api.example.test");
    expect(
      serverConfig({ WS_API_BASE_URL: "http://localhost:8765" }).apiBaseUrl
        .port,
    ).toBe("8765");
  });

  it("refuses plain http to other hosts, credentials and invalid URLs", () => {
    expect(() =>
      serverConfig({ WS_API_BASE_URL: "http://api.example.test" }),
    ).toThrow(/https/);
    expect(() =>
      serverConfig({ WS_API_BASE_URL: "https://user:pass@api.example.test" }),
    ).toThrow(/credentials/);
    expect(() => serverConfig({ WS_API_BASE_URL: "not a url" })).toThrow(
      /valid URL/,
    );
  });
});

describe("forexStreamUrl", () => {
  it("defaults to the API's own address with the websocket scheme", () => {
    expect(serverConfig({}).forexStreamUrl).toBe(
      "ws://127.0.0.1:8000/api/v1/forex/stream",
    );
    expect(
      serverConfig({ WS_API_BASE_URL: "https://api.example.test" })
        .forexStreamUrl,
    ).toBe("wss://api.example.test/api/v1/forex/stream");
  });

  it("accepts wss, and ws only to a loopback address", () => {
    expect(
      serverConfig({
        WS_FOREX_STREAM_URL: "wss://stream.example.test/api/v1/forex/stream",
      }).forexStreamUrl,
    ).toContain("wss://stream.example.test");
    expect(() =>
      serverConfig({ WS_FOREX_STREAM_URL: "ws://stream.example.test/x" }),
    ).toThrow(/wss/);
    expect(() =>
      serverConfig({ WS_FOREX_STREAM_URL: "https://stream.example.test/x" }),
    ).toThrow(/wss/);
  });

  it("refuses credentials, a query or a fragment, since a ticket or token never goes in a URL", () => {
    expect(() =>
      serverConfig({ WS_FOREX_STREAM_URL: "wss://u:p@stream.example.test/x" }),
    ).toThrow(/credentials/);
    expect(() =>
      serverConfig({
        WS_FOREX_STREAM_URL: "wss://stream.example.test/x?token=abc",
      }),
    ).toThrow(/query/);
    expect(() => serverConfig({ WS_FOREX_STREAM_URL: "not a url" })).toThrow(
      /valid URL/,
    );
  });
});

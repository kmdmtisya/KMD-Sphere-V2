import { describe, expect, it } from "vitest";

import {
  applyFrame,
  backoff,
  createStream,
  emptyState,
  type ConnectionStatus,
  type Frame,
  type Quote,
  type SocketLike,
} from "./stream";

const quote = (
  instrument: string,
  bid: string,
  over: Partial<Quote> = {},
): Quote =>
  ({
    instrument,
    provider: "sim",
    bid,
    ask: "1.1",
    mid: "1.05",
    mid_derived: true,
    ts_provider: null,
    ts_received: null,
    age_seconds: 1,
    data_type: "simulated",
    quality: "ok",
    freshness: "fresh",
    feed_status: "connected",
    ...over,
  }) as Quote;

describe("applyFrame", () => {
  it("keeps decimal strings exactly and follows the feed status", () => {
    let s = applyFrame(emptyState(), {
      type: "ready",
      max_instruments: 20,
      notice: "Places no trades.",
    });
    expect(s.notice).toBe("Places no trades.");
    s = applyFrame(s, {
      type: "subscribed",
      instruments: ["EUR_USD"],
      snapshot: [quote("EUR_USD", "1.08430")],
    });
    expect(s.quotes.EUR_USD.bid).toBe("1.08430");
    s = applyFrame(s, {
      type: "quote",
      ...quote("EUR_USD", "1.08440", { feed_status: "degraded" }),
    } as Frame);
    expect(s.quotes.EUR_USD.bid).toBe("1.08440");
    expect(s.feed).toBe("degraded");
    s = applyFrame(s, {
      type: "status",
      provider: "sim",
      feed_status: "disconnected",
    });
    expect(s.feed).toBe("disconnected");
  });
  it("drops pairs no longer followed and explains server errors in words", () => {
    let s = applyFrame(emptyState(), {
      type: "subscribed",
      instruments: ["A_B", "C_D"],
      snapshot: [quote("A_B", "1"), quote("C_D", "2")],
    });
    s = applyFrame(s, { type: "unsubscribed", instruments: ["C_D"] });
    expect(Object.keys(s.quotes)).toEqual(["C_D"]);
    s = applyFrame(s, { type: "error", code: "unknown_instrument" });
    expect(s.lastError).toMatch(/not offered/);
  });
});

describe("backoff", () => {
  it("doubles from one second to a ceiling of thirty", () => {
    expect([0, 1, 2, 3, 10].map(backoff)).toEqual([
      1000, 2000, 4000, 8000, 30000,
    ]);
  });
});

class FakeSocket implements SocketLike {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
  receive(frame: Frame) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

function harness(pairs: string[] = ["EUR_USD"]) {
  const sockets: FakeSocket[] = [];
  const timers: { fn: () => void; ms: number }[] = [];
  const statuses: ConnectionStatus[] = [];
  let minted = 0;
  const stream = createStream({
    instruments: () => pairs,
    onChange: (_s, status) => statuses.push(status),
    streamUrl: async () => "wss://stream.test/api/v1/forex/stream",
    mintTicket: async () => `ticket-${++minted}`,
    createSocket: () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s;
    },
    setTimer: (fn, ms) => timers.push({ fn, ms }),
    clearTimer: () => undefined,
  });
  const settle = () => new Promise((r) => setTimeout(r, 0));
  return { stream, sockets, timers, statuses, settle };
}

describe("createStream", () => {
  it("authenticates with a ticket, never a token or a URL parameter, then subscribes", async () => {
    const h = harness();
    h.stream.start();
    await h.settle();
    const ws = h.sockets[0];
    ws.onopen?.();
    expect(JSON.parse(ws.sent[0])).toEqual({
      type: "auth",
      ticket: "ticket-1",
    });
    ws.receive({ type: "ready", max_instruments: 20, notice: "n" });
    expect(JSON.parse(ws.sent[1])).toEqual({
      type: "subscribe",
      instruments: ["EUR_USD"],
    });
    expect(h.statuses.at(-1)).toBe("live");
  });

  it("mints a fresh ticket for each reconnect, and retries a lapsed session quickly", async () => {
    const h = harness();
    h.stream.start();
    await h.settle();
    h.sockets[0].onclose?.({ code: 4401 });
    expect(h.timers.at(-1)?.ms).toBe(500);
    h.timers.at(-1)?.fn();
    await h.settle();
    h.sockets[1].onopen?.();
    expect(JSON.parse(h.sockets[1].sent[0]).ticket).toBe("ticket-2");
  });

  it("backs off after an ordinary drop and stops when forex is switched off", async () => {
    const h = harness();
    h.stream.start();
    await h.settle();
    h.sockets[0].onclose?.({ code: 1006 });
    expect(h.timers.at(-1)?.ms).toBe(2000);
    h.timers.at(-1)?.fn();
    await h.settle();
    h.sockets[1].onclose?.({ code: 4404 });
    expect(h.statuses.at(-1)).toBe("unavailable");
    expect(h.timers).toHaveLength(1); // no further retry
  });

  it("does not reconnect after stop", async () => {
    const h = harness();
    h.stream.start();
    await h.settle();
    h.stream.stop();
    expect(h.statuses.at(-1)).toBe("stopped");
    expect(h.timers).toHaveLength(0);
  });
});

import { describe, expect, it } from "vitest";

import {
  applyEvent,
  createSseParser,
  isRefusal,
  newTurn,
  type ChatEvent,
} from "./chat";

const frame = (type: string, body: object) =>
  `event: ${type}\ndata: ${JSON.stringify({ type, ...body })}\n\n`;

function parse(chunks: string[]): ChatEvent[] {
  const seen: ChatEvent[] = [];
  const push = createSseParser((e) => seen.push(e));
  chunks.forEach(push);
  return seen;
}

describe("SSE parser", () => {
  it("reads complete frames in order", () => {
    const events = parse([
      frame("tool", { name: "get_net_worth", status: "running" }) +
        frame("token", { text: "Hello" }),
    ]);
    expect(events.map((e) => e.type)).toEqual(["tool", "token"]);
  });
  it("holds back a frame split across chunks, even in the middle of a word", () => {
    const whole = frame("token", { text: "Net worth is up" });
    const events = parse([
      whole.slice(0, 20),
      whole.slice(20, 40),
      whole.slice(40),
    ]);
    expect(events).toEqual([{ type: "token", text: "Net worth is up" }]);
  });
  it("accepts CRLF line endings", () => {
    const events = parse([
      frame("token", { text: "a" }).replace(/\n/g, "\r\n"),
    ]);
    expect(events).toHaveLength(1);
  });
  it("ignores unknown types and frames that are not JSON", () => {
    const events = parse([
      'event: ping\ndata: {"type":"ping"}\n\n',
      "data: not json\n\n",
      frame("token", { text: "ok" }),
    ]);
    expect(events).toEqual([{ type: "token", text: "ok" }]);
  });
});

describe("turn", () => {
  it("builds up the answer, the tools and the sources, then closes on done", () => {
    let turn = newTurn("t1", "What is my net worth?");
    const events: ChatEvent[] = [
      { type: "tool", name: "get_net_worth", status: "running" },
      { type: "tool", name: "get_net_worth", status: "ok" },
      {
        type: "source",
        tool: "get_net_worth",
        as_of: "2026-10-15T10:00:00Z",
        complete: true,
      },
      { type: "token", text: "Your " },
      { type: "token", text: "net worth." },
      {
        type: "done",
        conversation_id: "c1",
        message_id: "m1",
        model: "m",
        provider: "p",
        tool_calls: 1,
        structured: { observed: [{ text: "x", source: "get_net_worth" }] },
      },
    ];
    for (const e of events) turn = applyEvent(turn, e);
    expect(turn.text).toBe("Your net worth.");
    expect(turn.tools).toEqual([{ name: "get_net_worth", status: "ok" }]);
    expect(turn.sources).toEqual([
      { tool: "get_net_worth", asOf: "2026-10-15T10:00:00Z", complete: true },
    ]);
    expect(turn.done).toBe(true);
    expect(turn.conversationId).toBe("c1");
  });
  it("ends on an error with the server's message", () => {
    const turn = applyEvent(newTurn("t", "q"), {
      type: "error",
      code: "refused",
      message: "The assistant cannot answer that.",
    });
    expect(turn.error).toBe("The assistant cannot answer that.");
    expect(turn.done).toBe(true);
  });
  it("tells a refusal from an answer", () => {
    expect(isRefusal({ refusal: "trade_execution" })).toBe(true);
    expect(isRefusal({ observed: [] })).toBe(false);
    expect(isRefusal(null)).toBe(false);
  });
});

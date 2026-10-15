/**
 * The Copilot's streaming client (P14-T12.1). The answer arrives as server-sent events through the
 * BFF proxy (`/api/proxy/ai/chat`): `tool`, `source`, `token`, `done` and `error`. The text is
 * checked by the server before any of it is sent; the browser only parses and shows it. Figures
 * come from WealthSphere's tools, never from the model, and nothing here calculates money.
 */
import { csrf } from "@/lib/client/api";

export type ChatEvent =
  | { type: "token"; text: string }
  | {
      type: "tool";
      name: string;
      status: "running" | "ok" | "error";
      error_code?: string | null;
    }
  | { type: "source"; tool: string; as_of?: string | null; complete: boolean }
  | {
      type: "done";
      conversation_id: string;
      message_id: string;
      model: string;
      provider: string;
      tool_calls: number;
      structured?: StructuredAnswer | Refusal | null;
    }
  | {
      type: "error";
      code: "ai_unavailable" | "invalid_answer" | "refused";
      message: string;
    };

export type Cited = { text: string; source: string };
export type StructuredAnswer = {
  observed?: Cited[];
  calculated?: Cited[];
  assumptions?: string[];
  interpretation?: string;
  caveats?: string[];
  sources?: Record<string, unknown>[];
};
export type Refusal = { refusal: string };

export function isRefusal(
  value: StructuredAnswer | Refusal | null | undefined,
): value is Refusal {
  return !!value && "refusal" in value;
}

const TYPES = new Set(["token", "tool", "source", "done", "error"]);

/** Splits a stream of text chunks into complete events. Holds back a partial frame until it ends. */
export function createSseParser(
  onEvent: (event: ChatEvent) => void,
): (chunk: string) => void {
  let buffer = "";
  return (chunk) => {
    buffer += chunk.replace(/\r\n/g, "\n");
    let end = buffer.indexOf("\n\n");
    while (end !== -1) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) {
        try {
          const event = JSON.parse(data) as ChatEvent;
          if (TYPES.has(event.type)) onEvent(event);
        } catch {
          // A frame that is not valid JSON is ignored rather than shown.
        }
      }
      end = buffer.indexOf("\n\n");
    }
  };
}

export type Turn = {
  id: string;
  question: string;
  text: string;
  tools: { name: string; status: "running" | "ok" | "error" }[];
  sources: { tool: string; asOf: string | null; complete: boolean }[];
  structured: StructuredAnswer | Refusal | null;
  error: string | null;
  conversationId: string | null;
  done: boolean;
};

export function newTurn(id: string, question: string): Turn {
  return {
    id,
    question,
    text: "",
    tools: [],
    sources: [],
    structured: null,
    error: null,
    conversationId: null,
    done: false,
  };
}

/** Folds one event into a turn (pure, so the order and the repeated frames are testable). */
export function applyEvent(turn: Turn, event: ChatEvent): Turn {
  switch (event.type) {
    case "token":
      return { ...turn, text: turn.text + event.text };
    case "tool": {
      const others = turn.tools.filter((t) => t.name !== event.name);
      return {
        ...turn,
        tools: [...others, { name: event.name, status: event.status }],
      };
    }
    case "source":
      return {
        ...turn,
        sources: [
          ...turn.sources,
          {
            tool: event.tool,
            asOf: event.as_of ?? null,
            complete: event.complete,
          },
        ],
      };
    case "done":
      return {
        ...turn,
        done: true,
        conversationId: event.conversation_id,
        structured: event.structured ?? null,
      };
    case "error":
      return { ...turn, done: true, error: event.message };
  }
}

export type AskOptions = {
  conversationId?: string | null;
  portfolioId?: string | null;
  signal?: AbortSignal;
};

/** Sends a question and reports each event as it arrives. Resolves when the stream ends. */
export async function ask(
  message: string,
  options: AskOptions,
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const headers: Record<string, string> = {
    accept: "text/event-stream",
    "content-type": "application/json",
  };
  const token = csrf();
  if (token) headers["x-csrf-token"] = token;
  const response = await fetch("/api/proxy/ai/chat", {
    method: "POST",
    headers,
    signal: options.signal,
    body: JSON.stringify({
      message,
      conversation_id: options.conversationId ?? null,
      scope: options.portfolioId ? { portfolio_id: options.portfolioId } : null,
    }),
  });
  if (!response.ok || !response.body) {
    const messages: Record<number, string> = {
      401: "Your session has ended. Sign in again.",
      404: "That portfolio or conversation was not found.",
      422: "That question could not be sent. Shorten it and try again.",
      429: "You have reached the question limit for now. Try again later.",
      503: "The assistant is unavailable right now. Please try again shortly.",
    };
    onEvent({
      type: "error",
      code: "ai_unavailable",
      message:
        messages[response.status] ??
        "The assistant could not be reached. Try again.",
    });
    return;
  }
  const parse = createSseParser(onEvent);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parse(value);
  }
}

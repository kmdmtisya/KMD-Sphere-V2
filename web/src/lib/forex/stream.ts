/**
 * The live-quotes client (P14-T13.3). The browser never holds the access token: for each
 * connection it asks the portal for a single-use ticket (30 seconds), opens the socket at the
 * address the portal gives it, and sends `{"type":"auth","ticket":...}` as the first message. Nothing
 * secret is ever in the URL. Quotes are shown exactly as the API sends them (decimal strings), with
 * their freshness and data type; this module calculates nothing.
 *
 * Protocol: backend/app/modules/forex/stream_api.py.
 */
import type { components } from "@/lib/api";

export type Quote = components["schemas"]["QuoteOut"];
export type FeedStatus = Quote["feed_status"];

export type Frame =
  | { type: "ready"; max_instruments: number; notice: string }
  | { type: "subscribed"; instruments: string[]; snapshot: Quote[] }
  | { type: "unsubscribed"; instruments: string[] }
  | ({ type: "quote" } & Quote)
  | { type: "status"; provider: string; feed_status: FeedStatus }
  | { type: "heartbeat"; ts: string }
  | { type: "pong" }
  | { type: "error"; code: string };

export type StreamState = {
  quotes: Record<string, Quote>;
  feed: FeedStatus | null;
  notice: string | null;
  maxInstruments: number | null;
  lastError: string | null;
  lastHeartbeat: string | null;
};

export const emptyState = (): StreamState => ({
  quotes: {},
  feed: null,
  notice: null,
  maxInstruments: null,
  lastError: null,
  lastHeartbeat: null,
});

const ERRORS: Record<string, string> = {
  unknown_message: "The server did not understand a message.",
  invalid_instruments: "Those instruments are not valid.",
  too_many_instruments:
    "That is more instruments than one connection can follow.",
  unknown_instrument: "One of those instruments is not offered.",
};

/** Folds one server frame into the state (pure). */
export function applyFrame(state: StreamState, frame: Frame): StreamState {
  switch (frame.type) {
    case "ready":
      return {
        ...state,
        notice: frame.notice,
        maxInstruments: frame.max_instruments,
        lastError: null,
      };
    case "subscribed": {
      const quotes = { ...state.quotes };
      for (const q of frame.snapshot) quotes[q.instrument] = q;
      return { ...state, quotes };
    }
    case "unsubscribed": {
      const keep = new Set(frame.instruments);
      return {
        ...state,
        quotes: Object.fromEntries(
          Object.entries(state.quotes).filter(([k]) => keep.has(k)),
        ),
      };
    }
    case "quote": {
      const { type: _type, ...quote } = frame;
      void _type;
      return {
        ...state,
        quotes: { ...state.quotes, [quote.instrument]: quote },
        feed: quote.feed_status,
      };
    }
    case "status":
      return { ...state, feed: frame.feed_status };
    case "heartbeat":
      return { ...state, lastHeartbeat: frame.ts };
    case "error":
      return {
        ...state,
        lastError: ERRORS[frame.code] ?? "The server reported a problem.",
      };
    default:
      return state;
  }
}

export type ConnectionStatus =
  "connecting" | "live" | "reconnecting" | "unavailable" | "stopped";

/** The subset of the browser WebSocket this client uses (so tests can supply a fake). */
export interface SocketLike {
  onopen: (() => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
  onerror: (() => void) | null;
  send(data: string): void;
  close(): void;
}

export type StreamOptions = {
  instruments: () => string[];
  onChange: (state: StreamState, status: ConnectionStatus) => void;
  streamUrl: () => Promise<string>;
  mintTicket: () => Promise<string>;
  createSocket?: (url: string) => SocketLike;
  setTimer?: (fn: () => void, ms: number) => number;
  clearTimer?: (id: number) => void;
};

const CLOSE_NOT_AUTHENTICATED = 4401;
const CLOSE_OFF = 4404;
const CLOSE_TOO_MANY = 4429;
const CLOSE_PROTOCOL = 1008;

/** Delay before the nth reconnect: 1 s doubling to 30 s. */
export const backoff = (attempt: number): number =>
  Math.min(30_000, 1_000 * 2 ** Math.max(0, attempt));

export function createStream(options: StreamOptions) {
  const setTimer = options.setTimer ?? ((fn, ms) => window.setTimeout(fn, ms));
  const clearTimer = options.clearTimer ?? ((id) => window.clearTimeout(id));
  const open =
    options.createSocket ??
    ((url) => new WebSocket(url) as unknown as SocketLike);
  let state = emptyState();
  let status: ConnectionStatus = "connecting";
  let socket: SocketLike | null = null;
  let timer: number | null = null;
  let attempt = 0;
  let stopped = false;

  const publish = (
    next?: Partial<{ state: StreamState; status: ConnectionStatus }>,
  ) => {
    if (next?.state) state = next.state;
    if (next?.status) status = next.status;
    options.onChange(state, status);
  };

  const retry = (delay: number) => {
    if (stopped) return;
    publish({ status: "reconnecting" });
    timer = setTimer(() => void connect(), delay);
  };

  async function connect() {
    if (stopped) return;
    publish({ status: attempt === 0 ? "connecting" : "reconnecting" });
    let url: string;
    let ticket: string;
    try {
      [url, ticket] = await Promise.all([
        options.streamUrl(),
        options.mintTicket(),
      ]);
    } catch {
      attempt += 1;
      retry(backoff(attempt));
      return;
    }
    if (stopped) return;
    const ws = open(url);
    socket = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "auth", ticket }));
    ws.onmessage = (event) => {
      let frame: Frame;
      try {
        frame = JSON.parse(String(event.data)) as Frame;
      } catch {
        return;
      }
      if (frame.type === "ready") {
        attempt = 0;
        const pairs = options.instruments();
        if (pairs.length)
          ws.send(JSON.stringify({ type: "subscribe", instruments: pairs }));
        publish({ state: applyFrame(state, frame), status: "live" });
      } else {
        publish({ state: applyFrame(state, frame) });
      }
    };
    ws.onerror = () => undefined; // a close event always follows
    ws.onclose = (event) => {
      if (socket !== ws) return;
      socket = null;
      if (stopped) return;
      if (event.code === CLOSE_OFF || event.code === CLOSE_PROTOCOL) {
        publish({ status: "unavailable" });
        return;
      }
      attempt += 1;
      // A new ticket is minted for every connection. An expired session (4401) is retried at once:
      // the portal refreshes its tokens, or answers that the user must sign in again.
      retry(
        event.code === CLOSE_NOT_AUTHENTICATED
          ? 500
          : event.code === CLOSE_TOO_MANY
            ? 30_000
            : backoff(attempt),
      );
    };
  }

  return {
    start() {
      stopped = false;
      void connect();
    },
    stop() {
      stopped = true;
      if (timer !== null) clearTimer(timer);
      socket?.close();
      socket = null;
      publish({ status: "stopped" });
    },
    /** Follows these pairs (the whole list), unsubscribing from those no longer wanted. */
    follow(next: string[], previous: string[]) {
      if (!socket || status !== "live") return;
      const added = next.filter((p) => !previous.includes(p));
      const removed = previous.filter((p) => !next.includes(p));
      if (added.length)
        socket.send(JSON.stringify({ type: "subscribe", instruments: added }));
      if (removed.length)
        socket.send(
          JSON.stringify({ type: "unsubscribe", instruments: removed }),
        );
    },
  };
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import type { components } from "@/lib/api";
import {
  applyEvent,
  ask,
  newTurn,
  type StructuredAnswer,
  type Turn,
} from "@/lib/ai/chat";
import { apiDelete, apiGet } from "@/lib/client/api";

import { Button } from "../controls/controls";
import { Field } from "../controls/forms";
import { ErrorState, LoadingState } from "../states/states";
import { AnswerView, SourceChips } from "./AnswerView";

type S = components["schemas"];

const SUGGESTIONS = [
  "How is my portfolio doing?",
  "What is my net worth?",
  "Am I on track for my goals?",
  "Where does my passive income come from?",
];
const TOOL_LABEL = (name: string) =>
  name.replace(/^get_/, "").replace(/_/g, " ");

/** The past messages of a stored conversation, as finished turns. */
function turnsFrom(detail: S["ConversationDetailOut"]): Turn[] {
  const turns: Turn[] = [];
  for (const m of detail.messages) {
    if (m.role === "user") turns.push(newTurn(m.id, m.content));
    else if (turns.length) {
      const last = turns[turns.length - 1];
      turns[turns.length - 1] = {
        ...last,
        text: m.content,
        structured: (m.structured as StructuredAnswer | null) ?? null,
        done: true,
        conversationId: detail.id,
      };
    }
  }
  return turns;
}

/**
 * The Copilot conversation (P14-T12.2), used on its own page and in the docked panel. The server
 * authorises every tool the assistant uses; this component streams the answer, shows which data it
 * used, and shows the validated answer in separated sections. It is not personal investment advice
 * and it cannot place trades.
 */
export function ChatPane({
  portfolioId = null,
  compact = false,
  suggestions = SUGGESTIONS,
}: {
  portfolioId?: string | null;
  compact?: boolean;
  suggestions?: string[];
}) {
  const queryClient = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement | null>(null);
  const conversations = useQuery({
    queryKey: ["ai-conversations"],
    queryFn: () => apiGet<S["ConversationOut"][]>("ai/conversations?limit=50"),
    staleTime: 30_000,
    enabled: !compact,
  });

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [turns]);
  useEffect(() => () => abort.current?.abort(), []);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setDraft("");
    setBusy(true);
    const id = crypto.randomUUID();
    setTurns((t) => [...t, newTurn(id, question)]);
    abort.current = new AbortController();
    try {
      await ask(
        question,
        { conversationId, portfolioId, signal: abort.current.signal },
        (event) => {
          if (event.type === "done") setConversationId(event.conversation_id);
          setTurns((all) =>
            all.map((t) => (t.id === id ? applyEvent(t, event) : t)),
          );
        },
      );
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        setTurns((all) =>
          all.map((t) =>
            t.id === id
              ? {
                  ...t,
                  done: true,
                  error: "The connection was lost. Ask again.",
                }
              : t,
          ),
        );
      }
    } finally {
      setTurns((all) =>
        all.map((t) => (t.id === id && !t.done ? { ...t, done: true } : t)),
      );
      setBusy(false);
      void queryClient.invalidateQueries({ queryKey: ["ai-conversations"] });
    }
  }

  const open = useMutation({
    mutationFn: (id: string) =>
      apiGet<S["ConversationDetailOut"]>(`ai/conversations/${id}`),
    onSuccess: (detail) => {
      setConversationId(detail.id);
      setTurns(turnsFrom(detail));
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiDelete(`ai/conversations/${id}`),
    onSuccess: () => {
      fresh();
      void queryClient.invalidateQueries({ queryKey: ["ai-conversations"] });
    },
  });
  function fresh() {
    abort.current?.abort();
    setTurns([]);
    setConversationId(null);
    setBusy(false);
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {!compact ? (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-56 flex-1">
            <Field label="Conversation">
              {(p) => (
                <select
                  {...p}
                  value={conversationId ?? ""}
                  onChange={(e) =>
                    e.target.value ? open.mutate(e.target.value) : fresh()
                  }
                >
                  <option value="">New conversation</option>
                  {(conversations.data ?? []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title ?? "Untitled"} · {c.updated_at.slice(0, 10)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <Button onClick={fresh}>New</Button>
          {conversationId ? (
            <Button
              variant="ghost"
              disabled={remove.isPending}
              onClick={() => remove.mutate(conversationId)}
            >
              Delete this conversation
            </Button>
          ) : null}
        </div>
      ) : null}
      {conversations.isError ? (
        <ErrorState
          message="Past conversations could not be loaded."
          onRetry={() => void conversations.refetch()}
        />
      ) : null}
      {open.isPending ? (
        <LoadingState label="Opening the conversation" lines={2} />
      ) : null}

      <div
        role="log"
        aria-label="Conversation"
        className="flex min-h-40 flex-1 flex-col gap-4 overflow-y-auto"
      >
        {turns.length === 0 ? (
          <div className="flex flex-col gap-3">
            <p className="text-fg-muted">
              Ask about your own portfolios, goals, income and net worth
              {portfolioId ? " (this portfolio is in scope)" : ""}. Figures come
              from WealthSphere&apos;s calculations; the assistant explains
              them.
            </p>
            <ul
              className="flex flex-wrap gap-2"
              aria-label="Suggested questions"
            >
              {suggestions.map((q) => (
                <li key={q}>
                  <Button onClick={() => void send(q)}>{q}</Button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {turns.map((t) => (
          <article
            key={t.id}
            aria-label={`Question: ${t.question}`}
            className="flex flex-col gap-2"
          >
            <p className="self-end rounded-[var(--ws-radius-card)] bg-primary px-3 py-2 text-on-primary">
              {t.question}
            </p>
            <div
              className="flex flex-col gap-2 rounded-[var(--ws-radius-card)] border border-divider p-3"
              aria-live={t.done ? "off" : "polite"}
              aria-busy={!t.done}
            >
              {t.tools.length ? (
                <ul className="flex flex-wrap gap-2" aria-label="Checks made">
                  {t.tools.map((tool) => (
                    <li
                      key={tool.name}
                      className="rounded-[var(--ws-radius-pill)] border border-line px-3 py-0.5 text-[length:var(--ws-font-size-caption)]"
                    >
                      {TOOL_LABEL(tool.name)}:{" "}
                      {tool.status === "running"
                        ? "checking…"
                        : tool.status === "ok"
                          ? "done"
                          : "could not run"}
                    </li>
                  ))}
                </ul>
              ) : null}
              {t.error ? (
                <p role="alert" className="font-semibold text-negative-text">
                  {t.error}
                </p>
              ) : t.done && t.structured ? (
                <AnswerView structured={t.structured} />
              ) : (
                <p className="whitespace-pre-wrap">
                  {t.text || (t.done ? "" : "Thinking…")}
                </p>
              )}
              <SourceChips sources={t.sources} />
            </div>
          </article>
        ))}
        <div ref={end} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
        className="flex flex-col gap-2"
      >
        <Field
          label="Ask a question"
          hint="Not personal investment advice. The assistant cannot place trades or promise returns."
        >
          {(p) => (
            <textarea
              {...p}
              rows={compact ? 2 : 3}
              maxLength={4000}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(draft);
                }
              }}
            />
          )}
        </Field>
        <div className="flex gap-2">
          <Button
            type="submit"
            variant="primary"
            disabled={busy || !draft.trim()}
          >
            {busy ? "Answering…" : "Send"}
          </Button>
          {busy ? (
            <Button onClick={() => abort.current?.abort()}>Stop</Button>
          ) : null}
        </div>
      </form>
    </div>
  );
}

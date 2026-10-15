"use client";

import { isRefusal, type StructuredAnswer, type Refusal } from "@/lib/ai/chat";

import { DataAsOfLabel } from "../figures/figures";

const REFUSALS: Record<string, string> = {
  trade_execution:
    "WealthSphere does not place trades or move money, and the assistant cannot do it for you.",
  guaranteed_returns:
    "No return can be guaranteed, so the assistant will not promise one.",
};

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-1">
      <h4 className="text-[length:var(--ws-font-size-caption)] font-semibold uppercase tracking-wide text-fg-muted">
        {title}
      </h4>
      {children}
    </section>
  );
}

/**
 * A validated Copilot answer in its four parts (AI Rules): what the data shows, what was calculated,
 * the assumptions used and the model's own interpretation, kept apart so a reader can tell fact from
 * opinion. Server-added caveats and the sources the answer rests on follow. The text is rendered as
 * text (never as HTML).
 */
export function AnswerView({
  structured,
}: {
  structured: StructuredAnswer | Refusal;
}) {
  if (isRefusal(structured)) {
    return (
      <p
        role="note"
        className="rounded-[var(--ws-radius-control)] border border-line p-3"
      >
        {REFUSALS[structured.refusal] ?? "The assistant cannot answer that."}
      </p>
    );
  }
  const {
    observed = [],
    calculated = [],
    assumptions = [],
    interpretation = "",
    caveats = [],
    sources = [],
  } = structured;
  return (
    <div className="flex flex-col gap-3">
      {observed.length ? (
        <Section title="What your data shows">
          <ul className="list-disc ps-5">
            {observed.map((c, i) => (
              <li key={i}>
                {c.text} <span className="text-fg-muted">({c.source})</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {calculated.length ? (
        <Section title="Calculated by WealthSphere">
          <ul className="list-disc ps-5">
            {calculated.map((c, i) => (
              <li key={i}>
                {c.text} <span className="text-fg-muted">({c.source})</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {assumptions.length ? (
        <Section title="Assumptions">
          <ul className="list-disc ps-5">
            {assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </Section>
      ) : null}
      {interpretation ? (
        <Section title="AI interpretation">
          <p>{interpretation}</p>
        </Section>
      ) : null}
      {caveats.length ? (
        <Section title="Keep in mind">
          <ul className="list-disc ps-5 text-fg-muted">
            {caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </Section>
      ) : null}
      {sources.length ? (
        <Section title="Sources">
          <ul className="text-fg-muted">
            {sources.map((s, i) => (
              <li key={i}>
                {Object.values(s)
                  .filter((v) => typeof v === "string")
                  .join(" · ")}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}

export function SourceChips({
  sources,
}: {
  sources: { tool: string; asOf: string | null; complete: boolean }[];
}) {
  if (!sources.length) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Data this answer rests on">
      {sources.map((s, i) => (
        <li
          key={i}
          className="flex items-center gap-1 rounded-[var(--ws-radius-pill)] border border-line px-3 py-1 text-[length:var(--ws-font-size-caption)]"
        >
          {s.tool.replace(/_/g, " ")}
          {s.asOf ? <DataAsOfLabel asOf={s.asOf} /> : null}
          {!s.complete ? (
            <span className="font-semibold">incomplete</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

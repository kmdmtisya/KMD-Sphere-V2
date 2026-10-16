"use client";

import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { plotNumber } from "@/lib/chart/plot-values";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  ApiError,
} from "@/lib/client/api";
import { formatMoney, formatPercent } from "@/lib/format/decimal";
import {
  emptyGoal,
  FREQUENCIES,
  goalFromApi,
  goalRequest,
  GOAL_TYPES,
  validateGoal,
  type Frequency,
  type GoalValues,
} from "@/lib/planning/forms";

import { Card } from "../cards/cards";
import { Button } from "../controls/controls";
import { Drawer, Field } from "../controls/forms";
import { isStale, STALE_MESSAGE, Versioned } from "../controls/Versioned";
import { DataAsOfLabel } from "../figures/figures";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
} from "../states/states";

type S = components["schemas"];
type Goal = S["GoalOut"];

const TYPE_LABEL = Object.fromEntries(
  GOAL_TYPES.map((t) => [t.value, t.label]),
);
const today = () => new Date().toISOString().slice(0, 10);

/**
 * Goals (P14-T10.3): create, edit and delete a goal, and see the progress and the contribution the
 * backend estimates. The status, percentages and required contribution are the server's; the page
 * only draws the bar. A projection is never presented as a guarantee.
 */
export function Goals() {
  const [editing, setEditing] = useState<Goal | "new" | null>(null);
  const goals = useQuery({
    queryKey: ["goals"],
    queryFn: () => apiGet<Goal[]>("goals"),
    staleTime: 30_000,
  });
  const progress = useQueries({
    queries: (goals.data ?? []).map((g) => ({
      queryKey: ["goal-progress", g.id],
      queryFn: () => apiGet<S["GoalProgressOut"]>(`goals/${g.id}/progress`),
      staleTime: 30_000,
    })),
  });

  if (goals.isPending) return <LoadingState label="Loading goals" />;
  if (goals.isError)
    return (
      <ErrorState
        message="Goals could not be loaded."
        onRetry={() => void goals.refetch()}
      />
    );

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            Goals
          </h1>
          <p className="text-fg-muted">
            Targets you are saving towards, with progress estimated by the
            backend.
          </p>
        </div>
        <Button variant="primary" onClick={() => setEditing("new")}>
          New goal
        </Button>
      </header>
      {goals.data.length === 0 ? (
        <EmptyState
          title="No goals yet"
          action={
            <Button variant="primary" onClick={() => setEditing("new")}>
              Create your first goal
            </Button>
          }
        >
          Set a target amount and date to see how close you are.
        </EmptyState>
      ) : (
        <ul className="grid gap-4 lg:grid-cols-2">
          {goals.data.map((g, i) => (
            <li key={g.id}>
              <GoalCard
                goal={g}
                progress={progress[i]}
                onEdit={() => setEditing(g)}
              />
            </li>
          ))}
        </ul>
      )}
      <GoalDrawer editing={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

function GoalCard({
  goal,
  progress,
  onEdit,
}: {
  goal: Goal;
  progress: ReturnType<
    typeof useQueries<
      { queryKey: string[]; queryFn: () => Promise<S["GoalProgressOut"]> }[]
    >
  >[number];
  onEdit: () => void;
}) {
  const p = progress?.data as S["GoalProgressOut"] | undefined;
  return (
    <Card
      title={goal.name}
      as="article"
      actions={
        <Button variant="ghost" onClick={onEdit}>
          Edit<span className="sr-only"> {goal.name}</span>
        </Button>
      }
    >
      <p className="mb-3 text-fg-muted">
        {TYPE_LABEL[goal.goal_type]} · target{" "}
        {formatMoney(goal.target.amount, goal.target.currency).text} by{" "}
        {goal.target_date}
        {goal.target_in_todays_money ? " (in today's money)" : ""}
      </p>
      {!p && progress?.isError ? (
        <p className="text-fg-muted">
          Progress could not be loaded for this goal.
        </p>
      ) : null}
      {!p && !progress?.isError ? (
        <LoadingState label={`Loading progress of ${goal.name}`} lines={2} />
      ) : null}
      {p ? <Progress p={p} /> : null}
    </Card>
  );
}

function Progress({ p }: { p: S["GoalProgressOut"] }) {
  const pct = Math.max(0, Math.min(100, plotNumber(p.progress_percent)));
  const status = p.reached
    ? "Reached"
    : p.overdue
      ? "Past its date"
      : p.status === "on_track"
        ? "On track"
        : "Behind";
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-semibold">{status}</span>
        <span className="tabular-nums">
          {formatPercent(p.progress_percent)} of the target
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={`${p.name} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        className="h-2 overflow-hidden rounded-full bg-divider"
      >
        <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <dl className="grid gap-3 sm:grid-cols-2">
        <Stat
          label="Saved so far"
          value={
            formatMoney(p.current_value.amount, p.current_value.currency).text
          }
        />
        <Stat
          label="Still to go"
          value={formatMoney(p.gap.amount, p.gap.currency).text}
        />
        <Stat label="Months left" value={String(p.months_left)} />
        <Stat
          label="Estimated to reach it"
          value={p.estimated_completion ?? "Not within the projection"}
        />
        {p.required_contribution ? (
          <Stat
            label="Contribution needed"
            value={
              formatMoney(
                p.required_contribution.amount,
                p.required_contribution.currency,
              ).text
            }
          />
        ) : null}
      </dl>
      {p.scenarios.length ? (
        <ul className="flex flex-wrap gap-2" aria-label="Projected outcomes">
          {p.scenarios.map((s) => (
            <li
              key={s.kind}
              className="rounded-[var(--ws-radius-pill)] border border-line px-3 py-1 text-[length:var(--ws-font-size-caption)]"
            >
              {s.kind === "conservative"
                ? "Cautious"
                : s.kind === "growth"
                  ? "Optimistic"
                  : "Base"}{" "}
              ({formatPercent(s.annual_return_percent)}):{" "}
              {formatMoney(s.projected_value.amount, p.target.currency).text},{" "}
              {s.reaches_target ? "reaches the target" : "falls short"}
            </li>
          ))}
        </ul>
      ) : null}
      {!p.value_complete ? (
        <p className="text-fg-muted">
          Some holdings have no price yet, so the saved amount may be
          understated.
        </p>
      ) : null}
      <div className="flex items-center justify-between gap-2">
        <DataAsOfLabel asOf={p.as_of} />
      </div>
      <DisclosurePanel title="About this estimate" notices={[p.notice]} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
        {label}
      </dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function GoalDrawer({
  editing,
  onClose,
}: {
  editing: Goal | "new" | null;
  onClose: () => void;
}) {
  return (
    <Drawer
      open={editing !== null}
      title={editing === "new" ? "New goal" : "Edit goal"}
      onClose={onClose}
    >
      {editing === "new" ? (
        <GoalForm key="new" goal={null} onDone={onClose} />
      ) : null}
      {editing && editing !== "new" ? (
        <Versioned<Goal> path={`goals/${editing.id}`}>
          {(record, etag, reload) => (
            <GoalForm
              goal={record}
              etag={etag}
              onStale={reload}
              onDone={onClose}
            />
          )}
        </Versioned>
      ) : null}
    </Drawer>
  );
}

function GoalForm({
  goal,
  etag = null,
  onStale,
  onDone,
}: {
  goal: Goal | null;
  etag?: string | null;
  onStale?: () => void;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<GoalValues>(() =>
    goal ? goalFromApi(goal) : emptyGoal(),
  );
  const [problems, setProblems] = useState<ReturnType<typeof validateGoal>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<{ reporting_currency: string }>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const portfolios = useQuery({
    queryKey: ["portfolios", { archived: false }],
    queryFn: () =>
      apiGet<S["PortfolioOut"][]>("portfolios?include_archived=false"),
    staleTime: 30_000,
  });
  const currency =
    goal?.target.currency ?? prefs.data?.reporting_currency ?? "USD";
  const set = <K extends keyof GoalValues>(key: K, value: GoalValues[K]) =>
    setValues((v) => ({ ...v, [key]: value }));
  const [stale, setStale] = useState(false);
  const fail = (e: unknown) => {
    setStale(isStale(e));
    setMessage(
      isStale(e)
        ? STALE_MESSAGE
        : e instanceof ApiError
          ? (e.detail ?? `The server refused this (${e.status}).`)
          : "This could not be sent. Try again.",
    );
  };
  const done = async () => {
    await queryClient.invalidateQueries();
    onDone();
  };
  const save = useMutation({
    mutationFn: () =>
      goal
        ? apiPatch(`goals/${goal.id}`, goalRequest(values, currency), {
            ifMatch: etag ?? undefined,
          })
        : apiPost("goals", goalRequest(values, currency)),
    onSuccess: done,
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: () => apiDelete(`goals/${goal!.id}`),
    onSuccess: done,
    onError: fail,
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validateGoal(values, today());
    // Editing keeps an existing date even when it has now passed.
    if (goal && values.targetDate === goal.target_date) delete found.targetDate;
    setProblems(found);
    setMessage(null);
    if (Object.keys(found).length === 0) save.mutate();
  }
  const rate = (
    field: "base" | "conservative" | "growth" | "inflation",
    label: string,
    hint?: string,
  ) => (
    <Field label={label} error={problems[field]} hint={hint}>
      {(p) => (
        <input
          {...p}
          inputMode="decimal"
          value={values[field]}
          onChange={(e) => set(field, e.target.value)}
        />
      )}
    </Field>
  );

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <Field label="Name" error={problems.name}>
        {(p) => (
          <input
            {...p}
            maxLength={100}
            value={values.name}
            onChange={(e) => set("name", e.target.value)}
          />
        )}
      </Field>
      <Field label="Type">
        {(p) => (
          <select
            {...p}
            value={values.type}
            onChange={(e) => set("type", e.target.value as GoalValues["type"])}
          >
            {GOAL_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label={`Target amount (${currency})`} error={problems.target}>
        {(p) => (
          <input
            {...p}
            inputMode="decimal"
            value={values.target}
            onChange={(e) => set("target", e.target.value)}
          />
        )}
      </Field>
      <Field label="Reach it by" error={problems.targetDate}>
        {(p) => (
          <input
            {...p}
            type="date"
            value={values.targetDate}
            onChange={(e) => set("targetDate", e.target.value)}
          />
        )}
      </Field>
      <label className="flex min-h-9 items-center gap-2">
        <input
          type="checkbox"
          checked={values.todaysMoney}
          onChange={(e) => set("todaysMoney", e.target.checked)}
        />
        The target is in today&apos;s money (adjust for inflation)
      </label>
      <Field
        label="Count this portfolio towards it"
        hint="Leave blank to count your whole net worth."
      >
        {(p) => (
          <select
            {...p}
            value={values.portfolioId}
            onChange={(e) => set("portfolioId", e.target.value)}
          >
            <option value="">All portfolios</option>
            {(portfolios.data ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
        )}
      </Field>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 font-semibold">Assumptions</legend>
        <Field
          label={`Contribution (${currency})`}
          error={problems.contribution}
        >
          {(p) => (
            <input
              {...p}
              inputMode="decimal"
              value={values.contribution}
              onChange={(e) => set("contribution", e.target.value)}
            />
          )}
        </Field>
        <Field label="How often">
          {(p) => (
            <select
              {...p}
              value={values.contributionFrequency}
              onChange={(e) =>
                set("contributionFrequency", e.target.value as Frequency)
              }
            >
              {FREQUENCIES.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        {rate("base", "Base return (% a year)")}
        {rate("conservative", "Cautious return (optional)")}
        {rate("growth", "Optimistic return (optional)")}
        {rate("inflation", "Inflation (% a year)")}
      </fieldset>
      {message ? (
        <p role="alert" className="font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      {stale && onStale ? (
        <Button onClick={onStale}>Load the latest version</Button>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending
            ? "Saving…"
            : goal
              ? "Save changes"
              : "Create the goal"}
        </Button>
        <Button onClick={onDone}>Cancel</Button>
        {goal ? (
          confirmDelete ? (
            <Button
              variant="primary"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              {remove.isPending ? "Deleting…" : "Yes, delete this goal"}
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
              Delete
            </Button>
          )
        ) : null}
      </div>
    </form>
  );
}

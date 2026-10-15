"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet } from "@/lib/client/api";

import { Card } from "../cards/cards";
import { Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { DataAsOfLabel } from "../figures/figures";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];

const FEATURE_LABEL: Record<string, string> = {
  forex: "Forex module",
  forex_feed: "Forex feed",
  assistant_provider: "Assistant provider",
  rate_limits: "Rate limits",
};

/**
 * Operator views (P14-T17, DEC-34): the health of the platform and aggregate counts, read-only, for
 * the support role. It shows no account's financial data, email or identifier. The menu entry is
 * hidden for everyone else, but the API is the control: it answers 403 without the role, and each
 * view is recorded in the audit trail.
 */
export function Operator() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header>
        <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
          Operator views
        </h1>
        <p className="text-fg-muted">
          Read-only platform status and audit activity. No account&apos;s
          financial data is shown here.
        </p>
      </header>
      <Status />
      <Audit />
    </div>
  );
}

function Status() {
  const status = useQuery({
    queryKey: ["operator-status"],
    queryFn: () => apiGet<S["OperatorStatusOut"]>("operator/status"),
    staleTime: 15_000,
    retry: false,
  });
  if (status.isPending) return <LoadingState label="Loading platform status" />;
  if (status.isError)
    return (
      <ErrorState
        message="The platform status could not be loaded. You may not have the support role."
        onRetry={() => void status.refetch()}
      />
    );
  const s = status.data;
  const failed = Object.entries(s.checks).filter(([, v]) => v === "failed");
  return (
    <div className="flex flex-col gap-4">
      <StatusBanner kind={failed.length ? "stale" : "info"}>
        <span role="status">
          {failed.length
            ? `Not healthy: ${failed.map(([k]) => k).join(", ")} failed its check.`
            : "All dependency checks pass."}
        </span>
      </StatusBanner>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Dependencies"
          actions={<DataAsOfLabel asOf={s.generated_at} />}
        >
          <dl className="grid gap-2">
            {Object.entries(s.checks).map(([name, value]) => (
              <Row
                key={name}
                label={name}
                value={value === "ok" ? "OK" : "Failed"}
              />
            ))}
            <Row label="Environment" value={s.environment} />
          </dl>
        </Card>
        <Card title="Optional modules">
          <dl className="grid gap-2">
            {Object.entries(s.features).map(([key, value]) => (
              <Row key={key} label={FEATURE_LABEL[key] ?? key} value={value} />
            ))}
          </dl>
        </Card>
        <Card title="Accounts" info="Counts only; no account is named">
          <dl className="grid gap-2">
            {Object.entries(s.users).map(([key, value]) => (
              <Row key={key} label={key} value={String(value)} />
            ))}
          </dl>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <CountsCard
          title={`Audit events, last ${s.window_hours} hours`}
          caption="Audit events by outcome"
          rows={s.audit_by_outcome}
        />
        <CountsCard
          title="Most frequent actions"
          caption="Most frequent audit actions"
          rows={s.audit_top_actions}
        />
        <CountsCard
          title={`Background jobs, last ${s.window_hours} hours`}
          caption="Background jobs by status"
          rows={s.jobs_by_status}
        />
        <CountsCard
          title="Job failures"
          caption="Failed jobs by job"
          rows={s.job_failures_by_job}
          empty="No job has failed in this period."
        />
      </div>
      <DisclosurePanel title="About these views" notices={[s.notice]} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="capitalize text-fg-muted">{label.replace(/_/g, " ")}</dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function CountsCard({
  title,
  caption,
  rows,
  empty = "Nothing in this period.",
}: {
  title: string;
  caption: string;
  rows: S["CountOut"][];
  empty?: string;
}) {
  return (
    <Card title={title}>
      {rows.length === 0 ? (
        <p className="text-fg-muted">{empty}</p>
      ) : (
        <DataGrid
          caption={caption}
          rowKey="name"
          rows={rows.map((r) => ({ name: r.name, count: String(r.count) }))}
          columns={[
            { key: "name", header: "Name" },
            { key: "count", header: "Count", align: "end" },
          ]}
        />
      )}
    </Card>
  );
}

function Audit() {
  const [outcome, setOutcome] = useState("");
  const [prefix, setPrefix] = useState("");
  const prefixOk = prefix === "" || /^[a-z][a-z0-9_.]*$/.test(prefix);
  const audit = useQuery({
    queryKey: ["operator-audit", outcome, prefix],
    queryFn: () =>
      apiGet<S["OperatorAuditItem"][]>(
        `operator/audit?limit=100${outcome ? `&outcome=${outcome}` : ""}${prefix ? `&action_prefix=${encodeURIComponent(prefix)}` : ""}`,
      ),
    enabled: prefixOk,
    staleTime: 15_000,
    retry: false,
  });
  return (
    <Card
      title="Audit trail"
      info="The newest events: what happened, not who or which record"
    >
      <div className="mb-3 flex flex-wrap items-end gap-4">
        <div className="min-w-40">
          <Field label="Outcome">
            {(p) => (
              <select
                {...p}
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              >
                <option value="">Any</option>
                <option value="success">Success</option>
                <option value="failure">Failure</option>
                <option value="denied">Denied</option>
              </select>
            )}
          </Field>
        </div>
        <div className="min-w-56">
          <Field
            label="Action starts with"
            error={
              prefixOk
                ? undefined
                : "Use lower-case letters, digits, dots and underscores."
            }
            hint="For example reports. or operator."
          >
            {(p) => (
              <input
                {...p}
                maxLength={60}
                value={prefix}
                onChange={(e) => setPrefix(e.target.value.trim())}
              />
            )}
          </Field>
        </div>
      </div>
      {audit.isPending && prefixOk ? (
        <LoadingState label="Loading the audit trail" lines={2} />
      ) : null}
      {audit.isError ? (
        <ErrorState
          message="The audit trail could not be loaded."
          onRetry={() => void audit.refetch()}
        />
      ) : null}
      {audit.data && audit.data.length === 0 ? (
        <EmptyState title="No events">
          No audit event matches these filters.
        </EmptyState>
      ) : null}
      {audit.data && audit.data.length > 0 ? (
        <DataGrid
          caption="Audit events"
          rowKey="id"
          rows={audit.data.map((a, i) => ({
            id: `${a.correlation_id ?? "x"}-${i}`,
            when: a.occurred_at.slice(0, 19).replace("T", " "),
            action: a.action,
            outcome: a.outcome,
            actor: a.actor_type,
            resource: a.resource_type ?? "",
            channel: a.channel ?? "",
          }))}
          columns={[
            { key: "when", header: "Time (UTC)" },
            { key: "action", header: "Action" },
            { key: "outcome", header: "Outcome" },
            { key: "actor", header: "Actor" },
            { key: "resource", header: "Resource" },
            { key: "channel", header: "Channel" },
          ]}
        />
      ) : null}
    </Card>
  );
}

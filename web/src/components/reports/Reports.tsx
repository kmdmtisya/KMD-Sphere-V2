"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet } from "@/lib/client/api";

import { Card } from "../cards/cards";
import { Button } from "../controls/controls";
import { Field } from "../controls/forms";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
} from "../states/states";

type S = components["schemas"];
type Format = "pdf" | "xlsx" | "csv";

const FORMAT_LABEL: Record<Format, string> = {
  pdf: "PDF (to read or print)",
  xlsx: "Excel (to work with)",
  csv: "CSV (plain data)",
};

/** The file name the server chose (Content-Disposition), else a sensible default. */
function fileNameFrom(header: string | null, fallback: string): string {
  const match = header ? /filename="([^"]+)"/.exec(header) : null;
  return match ? match[1] : fallback;
}

async function download(
  kind: string,
  format: Format,
  portfolioId: string | null,
  currency: string | null,
): Promise<string> {
  const params = new URLSearchParams({ format });
  if (portfolioId) params.set("portfolio_id", portfolioId);
  if (currency) params.set("currency", currency);
  const response = await fetch(
    `/api/proxy/reports/${kind}?${params.toString()}`,
    { headers: { accept: "*/*" } },
  );
  if (!response.ok) {
    let detail = "";
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? "";
    } catch {
      // not JSON
    }
    throw new Error(
      detail || `The report could not be made (${response.status}).`,
    );
  }
  const blob = await response.blob();
  const name = fileNameFrom(
    response.headers.get("content-disposition"),
    `wealthsphere-${kind}.${format}`,
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return name;
}

/**
 * Reports and exports (P14-T15): PDF, Excel and CSV files made by the backend from the same figures
 * as the screens, each with its as-of time, currency and disclosures. The file is built on the
 * server and downloaded; nothing is calculated here.
 */
export function Reports() {
  const reports = useQuery({
    queryKey: ["reports"],
    queryFn: () => apiGet<S["ReportInfo"][]>("reports"),
    staleTime: 3_600_000,
  });
  const portfolios = useQuery({
    queryKey: ["portfolios", { archived: false }],
    queryFn: () =>
      apiGet<S["PortfolioOut"][]>("portfolios?include_archived=false"),
    staleTime: 30_000,
  });
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <header>
        <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
          Reports
        </h1>
        <p className="text-fg-muted">
          Download your figures as a PDF, an Excel workbook or a CSV file. Each
          file shows when it was made, the currency and what the figures are
          based on.
        </p>
      </header>
      {reports.isPending || portfolios.isPending ? (
        <LoadingState label="Loading reports" />
      ) : null}
      {reports.isError || portfolios.isError ? (
        <ErrorState
          message="Reports could not be loaded."
          onRetry={() =>
            void Promise.all([reports.refetch(), portfolios.refetch()])
          }
        />
      ) : null}
      {reports.data && portfolios.data ? (
        <>
          <ul className="grid gap-4 lg:grid-cols-2">
            {reports.data.map((r) => (
              <li key={r.kind}>
                <ReportCard info={r} portfolios={portfolios.data} />
              </li>
            ))}
          </ul>
          <DisclosurePanel
            title="About reports"
            notices={[
              "Reports describe your own recorded data. They are not investment, tax or legal advice, and past performance does not predict future results.",
              "A figure marked incomplete leaves out what could not be priced or converted. Check the notes at the end of each file.",
            ]}
          />
        </>
      ) : null}
    </div>
  );
}

function ReportCard({
  info,
  portfolios,
}: {
  info: S["ReportInfo"];
  portfolios: S["PortfolioOut"][];
}) {
  const [format, setFormat] = useState<Format>("pdf");
  const [portfolio, setPortfolio] = useState<string>("");
  const [done, setDone] = useState<string | null>(null);
  const needs = info.needs_portfolio;
  const optionalPortfolio = info.kind === "income";
  const chosen = portfolio || (needs ? (portfolios[0]?.id ?? "") : "");
  const make = useMutation({
    mutationFn: () => download(info.kind, format, chosen || null, null),
    onMutate: () => setDone(null),
    onSuccess: setDone,
  });
  if (needs && portfolios.length === 0) {
    return (
      <Card title={info.title} as="article">
        <p className="text-fg-muted">{info.description}</p>
        <div className="mt-3">
          <EmptyState title="No portfolio yet">
            Create a portfolio to make this report.
          </EmptyState>
        </div>
      </Card>
    );
  }
  return (
    <Card title={info.title} as="article">
      <p className="mb-3 text-fg-muted">{info.description}</p>
      <div className="flex flex-col gap-3">
        {needs || optionalPortfolio ? (
          <Field
            label={optionalPortfolio ? "Portfolio (optional)" : "Portfolio"}
            hint={
              optionalPortfolio
                ? "Leave on All portfolios for the combined view"
                : undefined
            }
          >
            {(p) => (
              <select
                {...p}
                value={optionalPortfolio ? portfolio : chosen}
                onChange={(e) => setPortfolio(e.target.value)}
              >
                {optionalPortfolio ? (
                  <option value="">All portfolios</option>
                ) : null}
                {portfolios.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        ) : null}
        <Field label="Format">
          {(p) => (
            <select
              {...p}
              value={format}
              onChange={(e) => setFormat(e.target.value as Format)}
            >
              {(Object.keys(FORMAT_LABEL) as Format[]).map((f) => (
                <option key={f} value={f}>
                  {FORMAT_LABEL[f]}
                </option>
              ))}
            </select>
          )}
        </Field>
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            disabled={make.isPending}
            onClick={() => make.mutate()}
          >
            {make.isPending
              ? "Making the file…"
              : `Download ${info.title.toLowerCase()}`}
          </Button>
        </div>
        {done ? (
          <p role="status" className="text-fg-muted">
            Downloaded {done}.
          </p>
        ) : null}
        {make.isError ? (
          <p role="alert" className="font-semibold text-negative-text">
            {make.error.message}
          </p>
        ) : null}
      </div>
    </Card>
  );
}

"use client";

import {
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  sortFn_text,
  tableFeatures,
  useTable,
  type SortFn,
} from "@tanstack/react-table";
import { useMemo } from "react";

import { compareDecimalStrings, formatMoney } from "@/lib/format/decimal";

import { Icon } from "../ui/Icon";

/**
 * Data grid (TanStack Table v9, ADR-0018) with real table semantics, sortable headers announced with
 * `aria-sort`, money columns sorted exactly as decimal strings, and a card list under 768 px instead
 * of a shrunken table (WEB_UI_UX_SPECIFICATION.md §4). Server pagination, column resizing and saved
 * views arrive with the module tasks that need them (P14-T08).
 */
export type GridColumn<T> = {
  key: keyof T & string;
  header: string;
  /** "money" values are decimal strings shown in `currencyKey`'s currency and sorted exactly. */
  kind?: "text" | "money" | "date";
  currencyKey?: keyof T & string;
  align?: "start" | "end";
  /** A custom display for the cell (links, badges, actions); sorting still uses the value of `key`. */
  render?: (row: T) => React.ReactNode;
};

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { text: sortFn_text },
});

type Row = Record<string, string>;
const helper = createColumnHelper<typeof features, Row>();

const decimalSort: SortFn<typeof features, Row> = (a, b, id) =>
  compareDecimalStrings(a.getValue<string>(id), b.getValue<string>(id));

function display<T extends Row>(row: T, column: GridColumn<T>, locale: string): React.ReactNode {
  if (column.render) return column.render(row);
  const value = row[column.key];
  if (column.kind === "money" && column.currencyKey) return formatMoney(value, row[column.currencyKey], locale).text;
  if (column.kind === "date") return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(value));
  return value;
}

export function DataGrid<T extends Row>({
  caption,
  columns,
  rows,
  rowKey,
  locale = "en",
}: {
  caption: string;
  columns: GridColumn<T>[];
  rows: T[];
  rowKey: keyof T & string;
  locale?: string;
}) {
  const columnDefs = useMemo(
    () =>
      helper.columns(
        columns.map((c) =>
          helper.accessor(c.key, {
            id: c.key,
            header: c.header,
            sortFn: c.kind === "money" ? decimalSort : "text",
            cell: (ctx) => display(ctx.row.original as T, c, locale) as string,
          }),
        ),
      ),
    [columns, locale],
  );
  const table = useTable({ features, columns: columnDefs, data: rows as Row[], getRowId: (r) => r[rowKey] });
  const byKey = useMemo(() => new Map(columns.map((c) => [c.key, c])), [columns]);
  const sortedRows = table.getRowModel().rows;

  return (
    <div>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-[length:var(--ws-font-size-body)]">
          <caption className="sr-only">{caption}</caption>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id} className="border-b border-divider">
                {group.headers.map((header) => {
                  const column = byKey.get(header.column.id as keyof T & string);
                  const sorted = header.column.getIsSorted();
                  const end = column?.align === "end" || column?.kind === "money";
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}
                      className={`h-9 px-3 text-[length:var(--ws-font-size-label)] font-semibold text-fg-muted ${end ? "text-end" : "text-start"}`}
                    >
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className={`inline-flex items-center gap-1 rounded-sm hover:text-fg ${end ? "flex-row-reverse" : ""}`}
                      >
                        {column?.header}
                        <Icon name={sorted === "asc" ? "arrowUp" : sorted === "desc" ? "arrowDown" : "sort"} size={12} />
                      </button>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {sortedRows.map((row) => (
              <tr key={row.id} className="h-9 border-b border-divider last:border-0 hover:bg-surface-elevated">
                {row.getAllCells().map((cell) => {
                  const column = byKey.get(cell.column.id as keyof T & string);
                  const end = column?.align === "end" || column?.kind === "money";
                  return (
                    <td key={cell.id} className={`px-3 ${end ? "text-end tabular-nums" : "text-start"}`}>
                      <table.FlexRender cell={cell} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul aria-label={caption} className="flex flex-col gap-2 md:hidden">
        {sortedRows.map((row) => (
          <li key={row.id} className="rounded-[var(--ws-radius-control)] border border-divider p-3">
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
              {columns.map((c) => (
                <div key={c.key} className="contents">
                  <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">{c.header}</dt>
                  <dd className={`text-end ${c.kind === "money" ? "tabular-nums font-medium" : ""}`}>
                    {display(row.original as T, c, locale)}
                  </dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}

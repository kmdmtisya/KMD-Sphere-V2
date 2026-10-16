"use client";

import { useQuery } from "@tanstack/react-query";

import { apiGetVersioned } from "@/lib/client/api";

import { ErrorState, LoadingState } from "../states/states";

/**
 * Loads one record fresh from the server, with the ETag of that version, before it is edited
 * (P14-T18.1). The form starts from what the server holds now (not from a list that may be old), and
 * sends the ETag back as `If-Match`, so an edit made on another device or channel in the meantime is
 * refused with a prompt to reload instead of being overwritten.
 */
export function Versioned<T>({
  path,
  children,
}: {
  path: string;
  children: (
    record: T,
    etag: string | null,
    reload: () => void,
  ) => React.ReactNode;
}) {
  const query = useQuery({
    queryKey: ["versioned", path],
    queryFn: () => apiGetVersioned<T>(path),
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
  if (query.isPending)
    return <LoadingState label="Loading the latest version" lines={3} />;
  if (query.isError)
    return (
      <ErrorState
        message="This record could not be loaded."
        onRetry={() => void query.refetch()}
      />
    );
  // A refetch (after a conflict) gives the form a new key, so it starts again from the latest version.
  return (
    <div key={query.data.etag ?? "none"}>
      {children(query.data.data, query.data.etag, () => void query.refetch())}
    </div>
  );
}

/** The message shown when the server refused an edit because the record changed elsewhere. */
export const STALE_MESSAGE =
  "This was changed somewhere else since you opened it. Load the latest version, then make your change again.";

/** True when the server refused an edit because the record changed since it was loaded (409). */
export function isStale(error: unknown): boolean {
  return (
    error instanceof Error &&
    "status" in error &&
    (error as { status: number }).status === 409 &&
    /changed somewhere else/i.test(
      String((error as { detail?: string }).detail ?? ""),
    )
  );
}

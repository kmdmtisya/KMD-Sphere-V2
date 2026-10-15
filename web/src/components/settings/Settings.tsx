"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  ApiError,
} from "@/lib/client/api";
import {
  profileChanges,
  profileFromApi,
  validateProfile,
  type ProfileValues,
} from "@/lib/settings/profile-form";

import { Card } from "../cards/cards";
import { Button } from "../controls/controls";
import { Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { AppearanceSelector } from "../theme/appearance";
import { ErrorState, LoadingState } from "../states/states";

type S = components["schemas"];
type SessionInfo = {
  signedIn: boolean;
  expiresAt?: { idle: string; absolute: string };
  accountUrl?: string;
};

const LOCALES = [
  { value: "en", label: "English" },
  { value: "en-GB", label: "English (United Kingdom)" },
  { value: "ar", label: "Arabic" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "es", label: "Spanish" },
];

function timeZones(): string[] {
  try {
    return (
      Intl as unknown as { supportedValuesOf: (k: string) => string[] }
    ).supportedValuesOf("timeZone");
  } catch {
    return [];
  }
}

/**
 * Profile, appearance, security and devices (P14-T16.1, T16.2). The profile is saved to the account
 * (so it follows you to every device); the password and multi-factor settings live with the
 * identity provider, reached by a link, and this page never sees a password or a token.
 */
export function Settings() {
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <header>
        <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
          Settings
        </h1>
        <p className="text-fg-muted">
          Your profile, how the portal looks, and the security of your account.
        </p>
      </header>
      <Profile />
      <RiskProfile />
      <Card
        title="Appearance"
        info="Saved to your account, so it applies on every device"
      >
        <AppearanceSelector />
      </Card>
      <Security />
      <Devices />
    </div>
  );
}

function Profile() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => apiGet<S["MeResponse"]>("me"),
    staleTime: 60_000,
  });
  if (me.isPending)
    return (
      <Card title="Profile">
        <LoadingState label="Loading your profile" lines={3} />
      </Card>
    );
  if (me.isError)
    return (
      <Card title="Profile">
        <ErrorState
          message="Your profile could not be loaded."
          onRetry={() => void me.refetch()}
        />
      </Card>
    );
  return <ProfileForm me={me.data} />;
}

function ProfileForm({ me }: { me: S["MeResponse"] }) {
  const queryClient = useQueryClient();
  const initial = profileFromApi(me);
  const [values, setValues] = useState<ProfileValues>(initial);
  const [problems, setProblems] = useState<ReturnType<typeof validateProfile>>(
    {},
  );
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(
    null,
  );
  const currencies = useQuery({
    queryKey: ["currencies"],
    queryFn: () => apiGet<S["CurrencyOut"][]>("currencies"),
    staleTime: 3_600_000,
  });
  const zones = timeZones();
  const set = <K extends keyof ProfileValues>(
    key: K,
    value: ProfileValues[K],
  ) => setValues((v) => ({ ...v, [key]: value }));
  const save = useMutation({
    mutationFn: () =>
      apiPatch<S["MeResponse"]>(
        "me/preferences",
        profileChanges(values, initial),
      ),
    onSuccess: async () => {
      setMessage({ ok: true, text: "Saved." });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (e) =>
      setMessage({
        ok: false,
        text:
          e instanceof ApiError
            ? (e.detail ?? `The change was refused (${e.status}).`)
            : "The change could not be saved. Try again.",
      }),
  });
  const changed = Object.keys(profileChanges(values, initial)).length > 0;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validateProfile(values);
    setProblems(found);
    setMessage(null);
    if (Object.keys(found).length === 0 && changed) save.mutate();
  }

  return (
    <Card title="Profile">
      <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
        <Field label="Email" hint="Managed by your sign-in account">
          {(p) => <input {...p} value={me.email ?? ""} readOnly />}
        </Field>
        <Field label="Display name" error={problems.displayName}>
          {(p) => (
            <input
              {...p}
              maxLength={100}
              value={values.displayName}
              onChange={(e) => set("displayName", e.target.value)}
            />
          )}
        </Field>
        <Field label="Time zone" error={problems.timezone}>
          {(p) => (
            <select
              {...p}
              value={values.timezone}
              onChange={(e) => set("timezone", e.target.value)}
            >
              {(zones.includes(values.timezone) || zones.length === 0
                ? zones
                : [values.timezone, ...zones]
              ).map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
              {zones.length === 0 ? (
                <option value={values.timezone}>{values.timezone}</option>
              ) : null}
            </select>
          )}
        </Field>
        <Field label="Language" error={problems.locale}>
          {(p) => (
            <select
              {...p}
              value={values.locale}
              onChange={(e) => set("locale", e.target.value)}
            >
              {(LOCALES.some((l) => l.value === values.locale)
                ? LOCALES
                : [{ value: values.locale, label: values.locale }, ...LOCALES]
              ).map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field
          label="Home currency"
          error={problems.baseCurrency}
          hint="The currency new portfolios start in"
        >
          {(p) => (
            <select
              {...p}
              value={values.baseCurrency}
              onChange={(e) => set("baseCurrency", e.target.value)}
            >
              {(
                currencies.data ?? [{ code: values.baseCurrency, name: "" }]
              ).map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field
          label="Country of residence"
          error={problems.residenceCountry}
          hint="Two letters, such as AE. It decides which investments are shown as eligible for you."
        >
          {(p) => (
            <input
              {...p}
              maxLength={2}
              value={values.residenceCountry}
              onChange={(e) =>
                set("residenceCountry", e.target.value.toUpperCase())
              }
            />
          )}
        </Field>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
          <Button
            type="submit"
            variant="primary"
            disabled={save.isPending || !changed}
          >
            {save.isPending ? "Saving…" : "Save changes"}
          </Button>
          {message ? (
            <p
              role={message.ok ? "status" : "alert"}
              className={
                message.ok
                  ? "text-fg-muted"
                  : "font-semibold text-negative-text"
              }
            >
              {message.text}
            </p>
          ) : null}
        </div>
      </form>
    </Card>
  );
}

function Security() {
  const csrf =
    typeof document === "undefined"
      ? ""
      : decodeURIComponent(
          /(?:^|; )__Host-ws_csrf=([^;]+)/.exec(document.cookie)?.[1] ?? "",
        );
  const session = useQuery({
    queryKey: ["web-session"],
    queryFn: async () =>
      (await (
        await fetch("/api/auth/session", {
          headers: { accept: "application/json" },
        })
      ).json()) as SessionInfo,
    staleTime: 30_000,
  });
  const when = (iso?: string) =>
    iso
      ? new Intl.DateTimeFormat("en", {
          dateStyle: "medium",
          timeStyle: "short",
        }).format(new Date(iso))
      : "";
  return (
    <Card
      title="Security and sessions"
      info="Passwords and multi-factor sign-in are managed by your sign-in provider"
    >
      <div className="flex flex-col gap-3">
        <p>
          Sign-in uses your organisation&apos;s secure sign-in page with
          multi-factor authentication. This browser holds no password or token:
          the portal keeps your session on its server and ends it after a period
          of inactivity.
        </p>
        {session.data?.expiresAt ? (
          <dl className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-0.5">
              <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
                This session ends if idle at
              </dt>
              <dd className="font-semibold tabular-nums">
                {when(session.data.expiresAt.idle)}
              </dd>
            </div>
            <div className="flex flex-col gap-0.5">
              <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
                This session ends at the latest at
              </dt>
              <dd className="font-semibold tabular-nums">
                {when(session.data.expiresAt.absolute)}
              </dd>
            </div>
          </dl>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          {session.data?.accountUrl ? (
            <a
              href={session.data.accountUrl}
              rel="noreferrer noopener"
              className="inline-flex min-h-9 items-center rounded-[var(--ws-radius-control)] border border-line px-4 font-semibold text-primary underline"
            >
              Change password or manage multi-factor sign-in
            </a>
          ) : null}
          <form method="post" action="/api/auth/logout">
            <input type="hidden" name="csrf" value={csrf} />
            <Button type="submit">Sign out of this browser</Button>
          </form>
        </div>
      </div>
    </Card>
  );
}

function Devices() {
  const queryClient = useQueryClient();
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => apiGet<S["DeviceOut"][]>("devices"),
    staleTime: 30_000,
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiDelete(`devices/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["devices"] }),
  });
  return (
    <Card
      title="Mobile devices"
      info="Phones that receive your alerts as push notifications"
    >
      {devices.isPending ? (
        <LoadingState label="Loading devices" lines={2} />
      ) : null}
      {devices.isError ? (
        <ErrorState
          message="Devices could not be loaded."
          onRetry={() => void devices.refetch()}
        />
      ) : null}
      {devices.data && devices.data.length === 0 ? (
        <p className="text-fg-muted">
          No mobile device is registered for push alerts. Sign in to the mobile
          app to add one.
        </p>
      ) : null}
      {devices.data && devices.data.length > 0 ? (
        <DataGrid
          caption="Registered mobile devices"
          rowKey="id"
          rows={devices.data.map((d) => ({
            id: d.id,
            platform: d.platform === "ios" ? "iPhone or iPad" : "Android",
            hint: `…${d.token_hint}`,
            seen: d.last_seen_at.slice(0, 10),
          }))}
          columns={[
            { key: "platform", header: "Device" },
            { key: "hint", header: "Token ends" },
            { key: "seen", header: "Last seen", kind: "date" },
            {
              key: "id",
              header: "Actions",
              render: (row) => (
                <Button
                  variant="ghost"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(row.id)}
                >
                  Remove
                  <span className="sr-only">
                    {" "}
                    {row.platform}, last seen {row.seen}
                  </span>
                </Button>
              ),
            },
          ]}
        />
      ) : null}
      {remove.isError ? (
        <p role="alert" className="mt-3 font-semibold text-negative-text">
          The device could not be removed. Try again.
        </p>
      ) : null}
    </Card>
  );
}

const TOLERANCES: {
  value: S["RiskProfileCreate"]["risk_tolerance"];
  label: string;
  help: string;
}[] = [
  {
    value: "conservative",
    label: "Conservative",
    help: "I prefer to protect what I have, even if growth is slower.",
  },
  {
    value: "balanced",
    label: "Balanced",
    help: "I accept some ups and downs for steady growth.",
  },
  {
    value: "growth",
    label: "Growth",
    help: "I accept larger swings for higher long-term growth.",
  },
  {
    value: "aggressive",
    label: "Aggressive",
    help: "I accept large swings and the chance of significant loss.",
  },
];

/**
 * Your own risk self-assessment (P14-T16.1). It is a statement you make, not advice: the platform
 * uses it to decide which research candidates are eligible and how to describe fit, and each change
 * is recorded as a new assessment so the history is kept.
 */
function RiskProfile() {
  const queryClient = useQueryClient();
  const profiles = useQuery({
    queryKey: ["risk-profiles"],
    queryFn: () => apiGet<S["RiskProfileOut"][]>("risk-profiles"),
    staleTime: 60_000,
  });
  const latest = profiles.data?.[0];
  const [tolerance, setTolerance] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(
    null,
  );
  const chosen = tolerance ?? latest?.risk_tolerance ?? "balanced";
  const years =
    horizon ??
    (latest?.horizon_years === null || latest?.horizon_years === undefined
      ? ""
      : String(latest.horizon_years));
  const yearsOk = years === "" || /^(100|\d{1,2})$/.test(years);
  const save = useMutation({
    mutationFn: () =>
      apiPost<S["RiskProfileOut"]>("risk-profiles", {
        risk_tolerance: chosen,
        horizon_years: years === "" ? null : Number(years),
      }),
    onMutate: () => setMessage(null),
    onSuccess: async () => {
      setMessage({ ok: true, text: "Recorded." });
      setTolerance(null);
      setHorizon(null);
      await queryClient.invalidateQueries({ queryKey: ["risk-profiles"] });
    },
    onError: (e) =>
      setMessage({
        ok: false,
        text:
          e instanceof ApiError
            ? (e.detail ?? `Refused (${e.status}).`)
            : "It could not be saved. Try again.",
      }),
  });
  if (profiles.isPending)
    return (
      <Card title="Risk profile">
        <LoadingState label="Loading" lines={2} />
      </Card>
    );
  if (profiles.isError)
    return (
      <Card title="Risk profile">
        <ErrorState
          message="Your risk profile could not be loaded."
          onRetry={() => void profiles.refetch()}
        />
      </Card>
    );
  const unchanged =
    latest &&
    chosen === latest.risk_tolerance &&
    (latest.horizon_years ?? "") === (years === "" ? "" : Number(years));
  return (
    <Card
      title="Risk profile"
      info="Your own description of the risk you are comfortable with; not a recommendation"
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 font-semibold">
          How would you describe your comfort with risk?
        </legend>
        {TOLERANCES.map((t) => (
          <label key={t.value} className="flex items-start gap-2">
            <input
              type="radio"
              name="risk-tolerance"
              className="mt-1"
              checked={chosen === t.value}
              onChange={() => setTolerance(t.value)}
            />
            <span>
              <span className="font-semibold">{t.label}</span>
              <span className="block text-fg-muted">{t.help}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <div className="mt-4 max-w-xs">
        <Field
          label="Investment horizon, in years (optional)"
          error={yearsOk ? undefined : "Enter whole years from 0 to 100."}
        >
          {(p) => (
            <input
              {...p}
              inputMode="numeric"
              value={years}
              onChange={(e) => setHorizon(e.target.value)}
            />
          )}
        </Field>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          disabled={save.isPending || !yearsOk || !!unchanged}
          onClick={() => save.mutate()}
        >
          {save.isPending
            ? "Saving�"
            : latest
              ? "Record a new assessment"
              : "Record my assessment"}
        </Button>
        {latest ? (
          <span className="text-fg-muted">
            Last recorded {latest.assessed_at.slice(0, 10)}.
          </span>
        ) : (
          <span className="text-fg-muted">Not recorded yet.</span>
        )}
        {message ? (
          <p
            role={message.ok ? "status" : "alert"}
            className={
              message.ok ? "text-fg-muted" : "font-semibold text-negative-text"
            }
          >
            {message.text}
          </p>
        ) : null}
      </div>
    </Card>
  );
}

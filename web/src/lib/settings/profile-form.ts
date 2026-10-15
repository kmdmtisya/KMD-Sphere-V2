/**
 * The profile form (P14-T16.1): typed text becomes a PATCH of `/me/preferences`. The backend
 * validates and stays the authority; these checks only avoid sending what it would refuse.
 */
import type { components } from "@/lib/api";

type S = components["schemas"];

export type ProfileValues = {
  displayName: string;
  timezone: string;
  locale: string;
  residenceCountry: string;
  baseCurrency: string;
};

export function profileFromApi(me: S["MeResponse"]): ProfileValues {
  return {
    displayName: me.display_name ?? "",
    timezone: me.timezone,
    locale: me.locale,
    residenceCountry: me.residence_country ?? "",
    baseCurrency: me.base_currency,
  };
}

export function validateProfile(
  v: ProfileValues,
): Partial<Record<keyof ProfileValues, string>> {
  const p: Partial<Record<keyof ProfileValues, string>> = {};
  const name = v.displayName.trim();
  if (name.length > 100) p.displayName = "Use 100 characters or fewer.";
  if (!v.timezone) p.timezone = "Choose a time zone.";
  if (!/^[a-z]{2,3}([_-][A-Za-z0-9]{2,8})*$/.test(v.locale))
    p.locale = "Use a language code such as en or en-GB.";
  if (v.residenceCountry && !/^[A-Z]{2}$/.test(v.residenceCountry))
    p.residenceCountry = "Use a two-letter country code such as AE or US.";
  if (!/^[A-Z]{3}$/.test(v.baseCurrency)) p.baseCurrency = "Choose a currency.";
  return p;
}

/** Only what changed is sent. A blank display name is not sent (the account keeps its name). */
export function profileChanges(
  now: ProfileValues,
  before: ProfileValues,
): S["PreferencesUpdate"] {
  const body: S["PreferencesUpdate"] = {};
  const name = now.displayName.trim();
  if (name && name !== before.displayName) body.display_name = name;
  if (now.timezone !== before.timezone) body.timezone = now.timezone;
  if (now.locale !== before.locale) body.locale = now.locale;
  if (now.baseCurrency !== before.baseCurrency)
    body.base_currency = now.baseCurrency;
  if (now.residenceCountry !== before.residenceCountry)
    body.residence_country = now.residenceCountry || null;
  return body;
}

import { describe, expect, it } from "vitest";

import {
  profileChanges,
  validateProfile,
  type ProfileValues,
} from "./profile-form";

const before: ProfileValues = {
  displayName: "Alice",
  timezone: "Asia/Dubai",
  locale: "en",
  residenceCountry: "AE",
  baseCurrency: "USD",
};

describe("profile form", () => {
  it("accepts the account's own values", () => {
    expect(validateProfile(before)).toEqual({});
  });
  it("explains a bad language code, country code or name", () => {
    expect(
      validateProfile({ ...before, locale: "English" }).locale,
    ).toBeTruthy();
    expect(
      validateProfile({ ...before, residenceCountry: "ae" }).residenceCountry,
    ).toBeTruthy();
    expect(
      validateProfile({ ...before, displayName: "x".repeat(101) }).displayName,
    ).toBeTruthy();
    expect(
      validateProfile({ ...before, baseCurrency: "usd" }).baseCurrency,
    ).toBeTruthy();
  });
  it("accepts a regional language code and an empty residence country", () => {
    expect(
      validateProfile({ ...before, locale: "en-GB", residenceCountry: "" }),
    ).toEqual({});
  });
  it("sends only what changed, and clears the residence country with null", () => {
    expect(profileChanges(before, before)).toEqual({});
    expect(
      profileChanges(
        { ...before, timezone: "Europe/London", displayName: " Alice B " },
        before,
      ),
    ).toEqual({ timezone: "Europe/London", display_name: "Alice B" });
    expect(profileChanges({ ...before, residenceCountry: "" }, before)).toEqual(
      { residence_country: null },
    );
  });
  it("never sends a blank display name", () => {
    expect(profileChanges({ ...before, displayName: "   " }, before)).toEqual(
      {},
    );
  });
});

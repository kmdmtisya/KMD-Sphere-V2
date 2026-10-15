import { describe, expect, it } from "vitest";

import { rolesFromToken } from "./current";

const jwt = (payload: unknown) => `h.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.s`;

describe("rolesFromToken", () => {
  it("reads the realm roles", () => {
    expect(rolesFromToken(jwt({ realm_access: { roles: ["user", "support"] } }))).toEqual(["user", "support"]);
  });
  it("returns none for missing or malformed tokens", () => {
    expect(rolesFromToken(jwt({}))).toEqual([]);
    expect(rolesFromToken("garbage")).toEqual([]);
    expect(rolesFromToken(jwt({ realm_access: { roles: "support" } }))).toEqual([]);
  });
});

import { apiPathFor } from "@/lib/bff/allowlist";

/**
 * BFF proxy skeleton (P14-T04). It validates every request against the allow-list. Forwarding with
 * the user's server-side token arrives with the session in P14-T05; until then nobody is signed in,
 * so nothing is forwarded.
 */
async function handle(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path } = await ctx.params;
  if (apiPathFor(request.method, path) === null) {
    return Response.json({ detail: "Not found" }, { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  return Response.json({ detail: "Not signed in" }, { status: 401, headers: { "Cache-Control": "no-store" } });
}

export { handle as DELETE, handle as GET, handle as PATCH, handle as POST, handle as PUT };

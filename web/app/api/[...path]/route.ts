// Same-origin proxy to the Argus API. The API address is read at runtime (API_INTERNAL_URL), so one web image
// can serve every client deployment, each pointing at its own API.
import type { NextRequest } from "next/server";

const upstream = () => process.env.API_INTERNAL_URL ?? "http://localhost:8000";

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const url = `${upstream()}/${path.join("/")}${req.nextUrl.search}`;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const res = await fetch(url, {
    method: req.method,
    headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
    body: hasBody ? await req.arrayBuffer() : undefined, // bytes, not text: uploads must arrive unchanged
    cache: "no-store",
  });
  const headers = new Headers();
  for (const h of ["content-type", "content-disposition", "content-length"]) {
    const v = res.headers.get(h);
    if (v) headers.set(h, v);
  }
  return new Response(res.body, { status: res.status, headers });
}

export { proxy as GET, proxy as POST, proxy as DELETE };

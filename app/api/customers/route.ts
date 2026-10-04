import { backend } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET(request: Request) {
  return backend(`/api/customers${new URL(request.url).search}`);
}

export async function POST(request: Request) {
  const body = await request.text();
  if (body.length > 8192) return Response.json({ error: "请求过大" }, { status: 413 });
  return backend("/api/customers", { method: "POST", headers: { "content-type": "application/json" }, body });
}

import { backend } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[0-9a-f-]{36}$/.test(id)) return Response.json({ error: "无效客户 ID" }, { status: 400 });
  return backend(`/api/customers/${id}`);
}

export async function PATCH(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[0-9a-f-]{36}$/.test(id)) return Response.json({ error: "无效客户 ID" }, { status: 400 });
  const body = await request.text();
  if (body.length > 8192) return Response.json({ error: "请求过大" }, { status: 413 });
  return backend(`/api/customers/${id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body });
}

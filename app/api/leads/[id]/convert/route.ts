import { backend } from "@/lib/backend";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[0-9a-f-]{36}$/.test(id)) return Response.json({ error: "无效潜客 ID" }, { status: 400 });
  const body = await request.text();
  if (body.length > 8192) return Response.json({ error: "请求过大" }, { status: 413 });
  return backend(`/api/leads/${id}/convert`, { method: "POST", headers: { "content-type": "application/json" }, body });
}

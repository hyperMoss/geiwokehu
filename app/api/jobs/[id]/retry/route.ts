import { backend } from "@/lib/backend";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[0-9a-f-]{36}$/.test(id)) {
    return Response.json({ error: "无效任务 ID" }, { status: 400 });
  }
  return backend(`/api/jobs/${id}/retry`, { method: "POST" });
}

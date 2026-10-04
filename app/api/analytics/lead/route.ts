import { backend } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const days = new URL(request.url).searchParams.get("days") ?? "30";
  if (!["7", "30", "90"].includes(days)) return Response.json({ error: "无效统计周期" }, { status: 400 });
  return backend(`/api/analytics/lead?days=${days}`);
}

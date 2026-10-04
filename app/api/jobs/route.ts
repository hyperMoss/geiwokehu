import { backend } from "@/lib/backend";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return backend("/api/jobs");
}

export async function POST(request: Request) {
  if (!request.headers.get("content-type")?.includes("application/json")) {
    return Response.json({ error: "只接受 JSON 请求" }, { status: 415 });
  }
  const body = await request.text();
  if (body.length > 8192) {
    return Response.json({ error: "请求过大" }, { status: 413 });
  }
  return backend("/api/jobs", { method: "POST", headers: { "content-type": "application/json" }, body });
}

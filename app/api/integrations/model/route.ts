import { backend } from "@/lib/backend";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return backend("/api/integrations/model");
}

export async function PUT(request: Request) {
  const body = await request.text();
  if (body.length < 2 || body.length > 8192) {
    return Response.json({ error: "请求过大或为空" }, { status: 413 });
  }
  return backend("/api/integrations/model", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body,
  });
}

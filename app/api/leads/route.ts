import { backend } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const query = new URL(request.url).search;
  return backend(`/api/leads${query}`);
}

import { backend } from "@/lib/backend";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return backend("/api/integrations/capabilities");
}

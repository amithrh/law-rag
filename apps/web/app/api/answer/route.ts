import { proxyToApi } from "../_proxy";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return proxyToApi(request, "/answer", "POST");
}

import { proxyToApi } from "../_proxy";

export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  const query = new URL(request.url).search;
  return proxyToApi(request, `/healthz${query}`, "GET");
}

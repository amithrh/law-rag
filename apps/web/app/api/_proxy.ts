import { TextDecoder } from "node:util";
import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";

const MAX_PROXY_BODY_BYTES = 16 * 1024;
const UPSTREAM_TIMEOUT_MS = 120_000;
const CLIENT_ID_COOKIE = "law-rag-client-id";
const CLIENT_ID_MAX_AGE = 60 * 60 * 24 * 30;

function apiBase(): string {
  return (
    process.env.LAW_RAG_API_URL ||
    process.env.API_INTERNAL_URL ||
    process.env.API_BASE ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

function apiKey(): string {
  return process.env.LAW_RAG_API_KEY || process.env.ANSWER_API_KEY || "";
}

function signClientId(clientId: string, secret: string): string {
  return `${clientId}.${createHmac("sha256", secret).update(clientId).digest("hex")}`;
}

function isSignedClientId(value: string, secret: string): boolean {
  if (!/^[A-Za-z0-9-]{16,64}\.[a-f0-9]{64}$/.test(value)) return false;
  const [clientId] = value.split(".", 1);
  const expected = Buffer.from(signClientId(clientId, secret));
  const actual = Buffer.from(value);
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

function clientIdentity(request: Request, secret: string): { value: string; setCookie: boolean } {
  const cookieHeader = request.headers.get("cookie") || "";
  const cookie = cookieHeader.split(";").map((item) => item.trim()).find((item) => item.startsWith(`${CLIENT_ID_COOKIE}=`));
  const value = cookie?.slice(`${CLIENT_ID_COOKIE}=`.length) || "";
  if (isSignedClientId(value, secret)) {
    return { value, setCookie: false };
  }
  return { value: signClientId(randomUUID(), secret), setCookie: true };
}

function attachClientCookie(
  response: Response,
  identity: { value: string; setCookie: boolean },
): Response {
  if (identity.setCookie) {
    const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
    response.headers.append(
      "Set-Cookie",
      `${CLIENT_ID_COOKIE}=${identity.value}; Path=/; Max-Age=${CLIENT_ID_MAX_AGE}; HttpOnly; SameSite=Lax${secure}`,
    );
  }
  return response;
}

async function readBoundedBody(request: Request): Promise<string> {
  const declared = request.headers.get("content-length");
  if (declared && Number(declared) > MAX_PROXY_BODY_BYTES) {
    throw new ProxyRequestError(413, "Request body is too large");
  }
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_PROXY_BODY_BYTES) {
        throw new ProxyRequestError(413, "Request body is too large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(body);
}

export class ProxyRequestError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

export async function proxyToApi(
  request: Request,
  path: string,
  method: "GET" | "POST",
): Promise<Response> {
  const key = apiKey();
  const identity = key
    ? clientIdentity(request, key)
    : { value: "", setCookie: false };
  const respond = (response: Response) => attachClientCookie(response, identity);
  if (process.env.NODE_ENV === "production" && !key) {
    return respond(Response.json(
      { detail: "The legal answer service is not configured securely." },
      { status: 503 },
    ));
  }

  let body = "";
  try {
    if (method === "POST") body = await readBoundedBody(request);
  } catch (error) {
    if (error instanceof ProxyRequestError) {
      return respond(Response.json({ detail: error.message }, { status: error.status }));
    }
    return respond(Response.json({ detail: "The request could not be read safely." }, { status: 400 }));
  }

  const headers = new Headers({
    Accept: method === "POST" ? "text/event-stream" : "application/json",
  });
  if (method === "POST") headers.set("Content-Type", "application/json");
  if (key) headers.set("X-Answer-Key", key);
  // The API trusts this opaque session identifier only when the shared API
  // key is configured. It keeps users behind the Next proxy from sharing one
  // rate-limit bucket without sending PII downstream.
  if (key) headers.set("X-Answer-Client", identity.value);

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase()}${path}`, {
      method,
      headers,
      body: method === "POST" ? body : undefined,
      cache: "no-store",
      // Propagate browser disconnects so the API can release its expensive
      // admission lease instead of waiting for the full upstream timeout.
      signal: AbortSignal.any([
        request.signal,
        AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      ]),
    });
  } catch {
    return respond(Response.json(
      { detail: "The legal answer service is temporarily unavailable." },
      { status: 503 },
    ));
  }

  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("Content-Type", contentType);
  responseHeaders.set("Cache-Control", "no-store, no-transform");
  responseHeaders.set("X-Accel-Buffering", "no");
  if (!upstream.ok) {
    return respond(Response.json(
      { detail: "The legal answer service rejected this request." },
      { status: upstream.status, headers: responseHeaders },
    ));
  }
  return respond(new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  }));
}

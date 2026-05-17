// Minimal SSE parser for fetch-streamed responses. We don't use the browser
// EventSource because EventSource is GET-only and doesn't allow JSON request
// bodies — the FastAPI /answer endpoint is POST.

export interface SsePacket {
  event: string;
  data: string;
}

export async function* readSse(
  response: Response,
  signal: AbortSignal,
): AsyncGenerator<SsePacket, void, unknown> {
  if (!response.body) throw new Error("response has no body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  try {
    while (true) {
      if (signal.aborted) return;
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // Split on blank lines (\n\n). Anything after the last \n\n is partial.
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const packet = parseBlock(block);
        if (packet) yield packet;
      }
    }
    if (buf.trim()) {
      const packet = parseBlock(buf);
      if (packet) yield packet;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // already released
    }
  }
}

function parseBlock(block: string): SsePacket | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const raw of block.split("\n")) {
    const line = raw.trimEnd();
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (!dataLines.length) return null;
  return { event, data: dataLines.join("\n") };
}

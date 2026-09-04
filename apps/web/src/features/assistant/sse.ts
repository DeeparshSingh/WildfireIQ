/**
 * A minimal Server-Sent Events reader over `fetch`.
 *
 * `EventSource` cannot POST, and the assistant's request carries the whole
 * transcript plus the user's view context — far too much for a query
 * string, and not something to put in a URL anyway. So the stream is read
 * by hand: frames are separated by a blank line, and within a frame the
 * `event:` and `data:` fields are what we care about.
 */

export type SseFrame = { event: string; data: unknown };

function parseFrame(raw: string): SseFrame | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue; // keepalive comment
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    // A single leading space after the colon is part of the framing, not the value.
    const value = separator === -1 ? "" : line.slice(separator + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }

  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

/**
 * Read an SSE response body, yielding one frame at a time.
 *
 * Chunk boundaries fall wherever the network puts them, so bytes are
 * buffered until a frame terminator appears rather than assuming a chunk
 * is a frame.
 */
export async function* readSse(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) return;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = parseFrame(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (frame) yield frame;
        boundary = buffer.indexOf("\n\n");
      }
    }
    // A server that closes without a trailing blank line still owes us its
    // last frame.
    const tail = parseFrame(buffer.trim());
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

/**
 * The browser's SSE reader.
 *
 * Chunk boundaries are the interesting part: a frame can be split across
 * network reads at any byte, and OpenRouter-style keepalive comments are
 * interleaved with the data. Getting either wrong drops an answer halfway
 * through, so both are pinned here.
 */
import { describe, expect, it } from "vitest";

import { readSse } from "@/features/assistant/sse";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(chunks: string[]) {
  const frames = [];
  for await (const frame of readSse(streamOf(chunks))) frames.push(frame);
  return frames;
}

describe("readSse", () => {
  it("parses named events with JSON payloads", async () => {
    const frames = await collect([
      'event: token\ndata: {"text":"Risk is "}\n\n',
      'event: token\ndata: {"text":"High."}\n\n',
      "event: done\ndata: {}\n\n",
    ]);
    expect(frames.map((f) => f.event)).toEqual(["token", "token", "done"]);
    expect(frames[0].data).toEqual({ text: "Risk is " });
  });

  it("reassembles a frame split across chunk boundaries", async () => {
    const frames = await collect(["event: tok", 'en\ndata: {"te', 'xt":"hi"}', "\n\n"]);
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ event: "token", data: { text: "hi" } });
  });

  it("delivers several frames arriving in one chunk", async () => {
    const frames = await collect([
      'event: tool_call\ndata: {"name":"get_weather"}\n\nevent: token\ndata: {"text":"ok"}\n\n',
    ]);
    expect(frames).toHaveLength(2);
    expect(frames[1].data).toEqual({ text: "ok" });
  });

  it("skips keepalive comments", async () => {
    const frames = await collect([
      ": OPENROUTER PROCESSING\n\n",
      'event: token\ndata: {"text":"x"}\n\n',
    ]);
    expect(frames).toHaveLength(1);
  });

  it("drops a malformed frame rather than throwing", async () => {
    const frames = await collect([
      "event: token\ndata: {not json}\n\n",
      'event: done\ndata: {"text":"fine"}\n\n',
    ]);
    expect(frames).toHaveLength(1);
    expect(frames[0].event).toBe("done");
  });

  it("emits a trailing frame that arrives without a terminator", async () => {
    const frames = await collect(['event: done\ndata: {"text":"end"}']);
    expect(frames).toHaveLength(1);
    expect(frames[0].data).toEqual({ text: "end" });
  });

  it("stops when the caller aborts", async () => {
    const controller = new AbortController();
    controller.abort();
    const frames = [];
    for await (const frame of readSse(
      streamOf(['event: token\ndata: {"text":"x"}\n\n']),
      controller.signal,
    )) {
      frames.push(frame);
    }
    expect(frames).toHaveLength(0);
  });
});

import { describe, expect, it, vi } from "vitest";

import { consumeAssistantSse } from "../src/features/assistant/sse";

function streamResponse(chunks: Uint8Array[]): Response {
  let index = 0;
  return new Response(
    new ReadableStream<Uint8Array>({
      pull(controller) {
        if (index === chunks.length) {
          controller.close();
          return;
        }
        controller.enqueue(chunks[index++]);
      },
    }),
    { status: 200 },
  );
}

describe("assistant SSE parser", () => {
  it("decodes split UTF-8, multiline data, CRLF, and ignores heartbeats", async () => {
    const bytes = new TextEncoder().encode(
      'event: snapshot\r\ndata: {"text":"caf\u00e9",\r\ndata: "sequence":0}\r\n\r\n: heartbeat\r\n\r\nevent: complete\r\ndata: {"ok":true}\r\n\r\n',
    );
    const splitInsideCharacter = bytes.indexOf(0xc3) + 1;
    const chunks = [
      bytes.slice(0, splitInsideCharacter),
      bytes.slice(splitInsideCharacter, splitInsideCharacter + 1),
      bytes.slice(splitInsideCharacter + 1),
    ];
    const events: unknown[] = [];
    const terminal = await consumeAssistantSse(streamResponse(chunks), (event) => events.push(event));
    expect(terminal).toBe(true);
    expect(events).toEqual([
      { event: "snapshot", data: { text: "café", sequence: 0 } },
      { event: "complete", data: { ok: true } },
    ]);
  });

  it("does not treat a truncated final frame as terminal", async () => {
    const response = streamResponse([
      new TextEncoder().encode('event: complete\ndata: {"ok":true}'),
    ]);
    const onEvent = vi.fn();
    expect(await consumeAssistantSse(response, onEvent)).toBe(false);
    expect(onEvent).not.toHaveBeenCalled();
  });
});

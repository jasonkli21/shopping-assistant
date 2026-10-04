export type AssistantEventName = "snapshot" | "delta" | "proposal" | "complete" | "error";

export interface AssistantSseEvent {
  event: string;
  data: unknown;
}

export async function consumeAssistantSse(
  response: Response,
  onEvent: (event: AssistantSseEvent) => void,
): Promise<boolean> {
  if (!response.ok || !response.body) {
    throw new Error(`Assistant stream failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];
  let terminal = false;

  const dispatch = () => {
    if (dataLines.length === 0) {
      eventName = "message";
      return;
    }
    const data = JSON.parse(dataLines.join("\n")) as unknown;
    onEvent({ event: eventName, data });
    if (eventName === "complete" || eventName === "error") terminal = true;
    eventName = "message";
    dataLines = [];
  };

  const consumeLines = (flush: boolean) => {
    while (buffer.length > 0) {
      const newline = buffer.search(/[\r\n]/);
      if (newline < 0) break;
      if (buffer[newline] === "\r" && newline === buffer.length - 1 && !flush) break;
      const line = buffer.slice(0, newline);
      const delimiterLength = buffer.startsWith("\r\n", newline) ? 2 : 1;
      buffer = buffer.slice(newline + delimiterLength);
      if (line === "") {
        dispatch();
        continue;
      }
      if (line.startsWith(":")) continue;
      const separator = line.indexOf(":");
      const field = separator < 0 ? line : line.slice(0, separator);
      let value = separator < 0 ? "" : line.slice(separator + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") eventName = value;
      if (field === "data") dataLines.push(value);
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      consumeLines(false);
    }
    buffer += decoder.decode();
    consumeLines(true);
    // An unterminated final frame is intentionally not dispatched. The caller
    // reloads durable history when no complete/error event was received.
    return terminal;
  } finally {
    reader.releaseLock();
  }
}

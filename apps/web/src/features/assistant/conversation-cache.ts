import { QueryClient } from "@tanstack/react-query";

import { MessagePage, MessageRead, ProposalRead } from "../../api/client";

export const messageKey = (projectId: string) => ["messages", projectId] as const;

export function handleStreamEvent(
  eventName: string,
  rawData: unknown,
  queryClient: QueryClient,
  projectId: string,
) {
  if (!isRecord(rawData)) return;
  if (eventName === "snapshot" && isRecord(rawData.message)) {
    upsertMessage(queryClient, projectId, rawData.message as unknown as MessageRead);
  } else if (eventName === "delta") {
    const messageId = rawData.message_id;
    const delta = rawData.delta;
    if (typeof messageId !== "string" || typeof delta !== "string") return;
    queryClient.setQueryData<MessagePage>(messageKey(projectId), (current) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((message) =>
          message.id === messageId
            ? { ...message, text: `${message.text}${delta}`, sequence: Number(rawData.sequence ?? message.sequence) }
            : message,
        ),
      };
    });
  } else if (eventName === "proposal" && isRecord(rawData.proposal)) {
    const proposal = rawData.proposal as unknown as ProposalRead;
    queryClient.setQueryData<MessagePage>(messageKey(projectId), (current) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((message) =>
          message.id === proposal.assistant_message_id ? { ...message, proposal } : message,
        ),
      };
    });
  } else if (eventName === "complete" && isRecord(rawData.message)) {
    upsertMessage(queryClient, projectId, rawData.message as unknown as MessageRead);
  }
}

function upsertMessage(
  queryClient: QueryClient,
  projectId: string,
  message: MessageRead,
) {
  queryClient.setQueryData<MessagePage>(messageKey(projectId), (current) => {
    const items = [...(current?.items ?? [])];
    const index = items.findIndex((item) => item.id === message.id);
    if (index < 0) items.push(message);
    else items[index] = message;
    items.sort((left, right) => left.ordinal - right.ordinal);
    return { items, next_cursor: current?.next_cursor ?? null };
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

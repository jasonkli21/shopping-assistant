import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MessagePage, MessageRead, Project, ProposalRead } from "../src/api/client";
import { AssistantPanel } from "../src/features/assistant/AssistantPanel";

const projectId = "6f16a208-307f-4dfc-8a2d-44aeb6df4d50";
const userMessageId = "a2b837ac-511a-4f86-9e76-2c988246c4e4";
const assistantMessageId = "c2cf6497-9e70-41b6-844d-418320c3ea18";
const proposalId = "d2cf6497-9e70-41b6-844d-418320c3ea18";
const timestamp = "2026-10-03T12:00:00Z";

function sampleProject(overrides: Partial<Project> = {}): Project {
  return {
    id: projectId,
    title: "Vacuum",
    goal: "Find a vacuum",
    category: null,
    status: "active",
    budget_target: null,
    budget_maximum: null,
    budget_currency: null,
    notes: null,
    reuse_preferences: false,
    revision: 1,
    created_at: timestamp,
    updated_at: timestamp,
    requirements: [],
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function completedMessage(proposal?: ProposalRead): MessageRead {
  return {
    id: assistantMessageId,
    conversation_id: "e2cf6497-9e70-41b6-844d-418320c3ea18",
    project_id: projectId,
    paired_message_id: userMessageId,
    ordinal: 2,
    role: "assistant",
    text: "I found a vacuum option for your review.",
    status: "completed",
    request_key: null,
    snapshot_revision: 1,
    sequence: 1,
    error_code: null,
    clarification_questions: ["Which currency should I use?"],
    created_at: timestamp,
    completed_at: timestamp,
    ...(proposal ? { proposal } : {}),
  };
}

function userMessage(text: string, requestKey: string): MessageRead {
  return {
    id: userMessageId,
    conversation_id: "e2cf6497-9e70-41b6-844d-418320c3ea18",
    project_id: projectId,
    paired_message_id: assistantMessageId,
    ordinal: 1,
    role: "user",
    text,
    status: "completed",
    request_key: requestKey,
    snapshot_revision: null,
    sequence: 0,
    error_code: null,
    clarification_questions: [],
    created_at: timestamp,
    completed_at: timestamp,
  };
}

function page(items: MessageRead[] = []): MessagePage {
  return { items, next_cursor: null };
}

function renderPanel(onProjectUpdate = vi.fn(), project = sampleProject()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <AssistantPanel
        project={project}
        onProjectUpdate={onProjectUpdate}
        onRevisionConflict={vi.fn(async () => null)}
      />
    </QueryClientProvider>,
  );
  return { queryClient, onProjectUpdate };
}

function sseResponse(message: MessageRead) {
  const data = [
    `event: snapshot\ndata: ${JSON.stringify({ message, sequence: 1, text: message.text })}\n\n`,
    `event: complete\ndata: ${JSON.stringify({ message })}\n\n`,
  ].join("");
  return new Response(data, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("assistant panel", () => {
  it("loads durable history, shows the proposal diff, and applies it explicitly", async () => {
    const appliedProject = sampleProject({ category: "Vacuum", budget_maximum: "400.00", budget_currency: "USD", revision: 2 });
    const proposal: ProposalRead = {
      id: proposalId,
      project_id: projectId,
      assistant_message_id: assistantMessageId,
      base_revision: 1,
      schema_version: 1,
      operations: {
        project_updates: { category: "Vacuum", budget_maximum: "400", budget_currency: "USD" },
        requirement_operations: [{ operation: "add", fields: { kind: "preference", label: "Works well with hair" } }],
      },
      status: "pending",
      applied_revision: null,
      applied_at: null,
      applied_project: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    let savedPage = page();
    const postedCommands: Array<Record<string, unknown>> = [];
    const onProjectUpdate = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/messages?") && !init?.method) return jsonResponse(savedPage);
      if (url.endsWith(`/projects/${projectId}/messages`) && init?.method === "POST") {
        const postedCommand = JSON.parse(String(init.body)) as Record<string, unknown>;
        postedCommands.push(postedCommand);
        savedPage = page([userMessage(String(postedCommand.text), String(postedCommand.request_key)), completedMessage(proposal)]);
        return jsonResponse({ user_message_id: userMessageId, assistant_message_id: assistantMessageId, conversation_id: "e2cf6497-9e70-41b6-844d-418320c3ea18", replayed: false }, 202);
      }
      if (url.includes("/messages/stream?")) return sseResponse(completedMessage(proposal));
      if (url.endsWith(`/proposals/${proposalId}/apply`)) {
        const appliedProposal = {
          ...proposal,
          status: "applied" as const,
          applied_revision: 2,
          applied_at: timestamp,
          applied_project: appliedProject,
        };
        savedPage = page([
          userMessage(String(postedCommands[0].text), String(postedCommands[0].request_key)),
          completedMessage(appliedProposal),
        ]);
        return jsonResponse({ proposal: appliedProposal, project: appliedProject, replayed: false });
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "request-key-00000001" });
    renderPanel(onProjectUpdate);

    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));
    expect(await screen.findByText("Tell me what you’re shopping for.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Your shopping request"), {
      target: { value: "I need a vacuum under $400 that is good with hair" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("AI suggestion")).toBeInTheDocument();
    expect(screen.getByText("Works well with hair")).toBeInTheDocument();
    expect(screen.getByText("Unknown → Vacuum")).toBeInTheDocument();
    expect(postedCommands[0].expected_version).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: "Apply suggestion" }));
    await waitFor(() => expect(onProjectUpdate).toHaveBeenCalledWith(appliedProject, false));
    expect(await screen.findByText("Applied at project revision 2.")).toBeInTheDocument();
  });

  it("retries an unacknowledged command with the same request key", async () => {
    let savedPage = page();
    const attempts: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/messages?") && !init?.method) return jsonResponse(savedPage);
      if (url.endsWith(`/projects/${projectId}/messages`) && init?.method === "POST") {
        const command = JSON.parse(String(init.body)) as Record<string, unknown>;
        attempts.push(command);
        if (attempts.length === 1) throw new TypeError("connection closed after save");
        savedPage = page([userMessage(String(command.text), String(command.request_key)), completedMessage()]);
        return jsonResponse({ user_message_id: userMessageId, assistant_message_id: assistantMessageId, conversation_id: "e2cf6497-9e70-41b6-844d-418320c3ea18", replayed: true }, 202);
      }
      if (url.includes("/messages/stream?")) return sseResponse(completedMessage());
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "request-key-00000002" });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));
    await screen.findByText("Tell me what you’re shopping for.");
    fireEvent.change(screen.getByLabelText("Your shopping request"), {
      target: { value: "Find a quiet vacuum" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("button", { name: "Retry same submission" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry same submission" }));

    expect(await screen.findByText("The same saved command was confirmed. Reconnecting to its response.")).toBeInTheDocument();
    expect(attempts).toHaveLength(2);
    expect(attempts[0].request_key).toBe(attempts[1].request_key);
  });

  it.each([
    [409, "conversation_busy", "Another assistant response is still being prepared."],
    [503, "generation_capacity", "The assistant is busy right now."],
  ])("restores text and creates a fresh command after a known %s rejection", async (status, code, message) => {
    const attempts: Array<Record<string, unknown>> = [];
    let savedPage = page();
    let key = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/messages?") && !init?.method) return jsonResponse(savedPage);
      if (url.endsWith(`/projects/${projectId}/messages`) && init?.method === "POST") {
        const command = JSON.parse(String(init.body)) as Record<string, unknown>;
        attempts.push(command);
        if (attempts.length === 1) {
          return jsonResponse({ error: { code, message: "Please retry shortly." } }, Number(status));
        }
        savedPage = page([
          userMessage(String(command.text), String(command.request_key)),
          completedMessage(),
        ]);
        return jsonResponse(
          {
            user_message_id: userMessageId,
            assistant_message_id: assistantMessageId,
            conversation_id: "e2cf6497-9e70-41b6-844d-418320c3ea18",
            replayed: false,
          },
          202,
        );
      }
      if (url.includes("/messages/stream?")) return sseResponse(completedMessage());
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => `request-key-${++key}` });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));
    await screen.findByText("Tell me what you’re shopping for.");
    fireEvent.change(screen.getByLabelText("Your shopping request"), {
      target: { value: "Find a quiet vacuum" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(new RegExp(message))).toBeInTheDocument();
    expect(screen.getByLabelText("Your shopping request")).toHaveValue("Find a quiet vacuum");
    expect(screen.queryByRole("button", { name: "Retry same submission" })).not.toBeInTheDocument();
    expect(sessionStorage.getItem(`shopping-assistant-message-attempt:${projectId}`)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Message saved. Preparing suggestions for review.")).toBeInTheDocument();
    expect(attempts).toHaveLength(2);
    expect(attempts[0].request_key).not.toBe(attempts[1].request_key);
    expect(attempts[1].text).toBe("Find a quiet vacuum");
  });

  it("keeps typed text when a pending retry discovers a revision conflict", async () => {
    const savedText = "Find a quiet vacuum for a small apartment";
    sessionStorage.setItem(
      `shopping-assistant-message-attempt:${projectId}`,
      JSON.stringify({ text: savedText, requestKey: "saved-request-key-0001", expectedVersion: 1 }),
    );
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/messages?") && !init?.method) return jsonResponse(page());
      if (url.endsWith(`/projects/${projectId}/messages`) && init?.method === "POST") {
        return jsonResponse(
          { error: { code: "revision_conflict", message: "Project changed." } },
          409,
        );
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));
    await screen.findByText("Tell me what you’re shopping for.");
    fireEvent.click(screen.getByRole("button", { name: "Retry same submission" }));

    expect(await screen.findByText(/project changed before this message was accepted/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Your shopping request")).toHaveValue(savedText);
  });

  it("loads older durable history and restores keyboard focus when the panel closes", async () => {
    const currentUser = { ...userMessage("Most recent request", "recent-request-key-0001"), ordinal: 3 };
    const currentAssistant = { ...completedMessage(), ordinal: 4 };
    const olderUser = {
      ...userMessage("My first saved shopping request", "old-request-key-0001"),
      id: "a2b837ac-511a-4f86-9e76-2c988246c4e5",
      ordinal: 1,
    };
    const olderAssistant = {
      ...completedMessage(),
      id: "c2cf6497-9e70-41b6-844d-418320c3ea19",
      paired_message_id: olderUser.id,
      ordinal: 2,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("before=older-page")) return jsonResponse(page([olderUser, olderAssistant]));
      if (url.includes("/messages?") && !init?.method) {
        return jsonResponse({ items: [currentUser, currentAssistant], next_cursor: "older-page" });
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    const toggle = screen.getByRole("button", { name: "Ask assistant" });
    fireEvent.click(toggle);
    await screen.findByText("Most recent request");
    expect(screen.getByLabelText("Your shopping request")).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Load earlier messages" }));
    expect(await screen.findByText("My first saved shopping request")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(toggle).toHaveFocus());
    expect(screen.queryByText("Tell me what you’re shopping for.")).not.toBeInTheDocument();
  });

  it("shows existing values in a requirement diff", async () => {
    const requirement: Project["requirements"][number] = {
      id: "f2cf6497-9e70-41b6-844d-418320c3ea19",
      project_id: projectId,
      kind: "must_have",
      label: "Quiet operation",
      detail: null,
      attribute_key: "noise",
      operator: "lte",
      value: 50,
      unit: "dB",
      position: 0,
      origin: "user",
      created_at: timestamp,
      updated_at: timestamp,
    };
    const proposal: ProposalRead = {
      id: proposalId,
      project_id: projectId,
      assistant_message_id: assistantMessageId,
      base_revision: 1,
      schema_version: 1,
      operations: {
        project_updates: {},
        requirement_operations: [
          { operation: "update", id: requirement.id, fields: { value: 40 } },
        ],
      },
      status: "pending",
      applied_revision: null,
      applied_at: null,
      applied_project: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    const savedMessages = page([
      userMessage("Make the vacuum quieter", "quiet-request-key-0001"),
      completedMessage(proposal),
    ]);
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/messages?")) return jsonResponse(savedMessages);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPanel(vi.fn(), sampleProject({ requirements: [requirement] }));
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));

    expect(await screen.findByText("AI suggestion")).toBeInTheDocument();
    expect(screen.getByText("Value: 50 → 40")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply suggestion" })).toBeInTheDocument();
  });

  it("disables apply for a suggestion prepared against an older revision", async () => {
    const staleProposal: ProposalRead = {
      id: proposalId,
      project_id: projectId,
      assistant_message_id: assistantMessageId,
      base_revision: 1,
      schema_version: 1,
      operations: { project_updates: { category: "Vacuum" }, requirement_operations: [] },
      status: "pending",
      applied_revision: null,
      applied_at: null,
      applied_project: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/messages?")) {
        return jsonResponse(page([
          userMessage("Find a vacuum", "stale-request-key-0001"),
          completedMessage(staleProposal),
        ]));
      }
      throw new Error(`Unexpected request: ${String(input)}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPanel(vi.fn(), sampleProject({ revision: 2 }));
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));

    expect(await screen.findByText("stale")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply suggestion" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss suggestion" })).toBeInTheDocument();
  });
});

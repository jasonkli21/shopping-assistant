export interface PendingAttempt {
  text: string;
  requestKey: string;
  expectedVersion: number;
}

export function readPendingAttempt(projectId: string): PendingAttempt | null {
  try {
    const value = sessionStorage.getItem(storageKey(projectId));
    if (!value) return null;
    const parsed = JSON.parse(value) as Partial<PendingAttempt>;
    return typeof parsed.text === "string" && typeof parsed.requestKey === "string" && Number.isInteger(parsed.expectedVersion)
      ? parsed as PendingAttempt
      : null;
  } catch {
    return null;
  }
}

export function persistPendingAttempt(projectId: string, attempt: PendingAttempt) {
  try {
    sessionStorage.setItem(storageKey(projectId), JSON.stringify(attempt));
  } catch {
    // The in-memory recovery affordance remains available when session storage is disabled.
  }
}

export function clearPendingAttempt(projectId: string) {
  try {
    sessionStorage.removeItem(storageKey(projectId));
  } catch {
    // The next history refresh remains authoritative.
  }
}

function storageKey(projectId: string) {
  return `shopping-assistant-message-attempt:${projectId}`;
}

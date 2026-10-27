export class AccountError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function accountApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new AccountError("Cannot reach Dark. Check your connection and try again.", 0);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new AccountError(
      typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.",
      response.status,
    );
  }
  return response.status === 204 ? undefined as T : response.json();
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

export type Account = { user: { id: string; email: string }; session: { kind: string } };
export type Device = { id: string; name: string; created_at: string; expires_at: string };
export type DesktopAssertion = {
  expected_text: string; observed_text: string | null; passed: boolean;
  step: number | null; match: "exact" | "contains";
};
export type DesktopReport = {
  status: string; finished_at: string; window_title: string; scenario: string | null;
  assertions: DesktopAssertion[]; reason: string | null; error: string | null; verified_finding: false;
};
export type Run = {
  id: string; target: string; goal: string; status: string; started_at: string;
  finished_at: string | null; kind: "scan" | "desktop"; desktop_report: DesktopReport | null;
};

export function loginDestination(): string {
  const requested = new URLSearchParams(window.location.search).get("next") || "/dashboard";
  // Only account destinations are accepted, including a CLI code carried through sign-in.
  try {
    const target = new URL(requested, window.location.origin);
    const allowed = ["/dashboard", "/connect"].includes(target.pathname)
      || /^\/dashboard\/runs\/[a-zA-Z0-9_-]{1,80}$/.test(target.pathname);
    if (target.origin === window.location.origin && allowed) {
      return target.pathname + target.search;
    }
  } catch { /* Use the dashboard for malformed destinations. */ }
  return "/dashboard";
}

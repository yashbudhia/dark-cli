export class AccountError extends Error {
  constructor(message: string, public status: number, public retryAfter?: number) {
    super(message);
  }
}

export async function accountApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  const timeout = setTimeout(abort, 20000);
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) abort();
  try {
    const response = await fetch(`/api${path}`, {
      ...options,
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
    if (response.status === 204) return undefined as T;
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const seconds = Number(response.headers.get("Retry-After"));
      throw new AccountError(
        typeof body?.detail === "string" ? body.detail : "Dark is temporarily unavailable. Please try again.",
        response.status,
        seconds > 0 && Number.isFinite(seconds) ? Math.ceil(seconds) : undefined,
      );
    }
    if (body === null) throw new AccountError("Dark returned an unreadable response. Please try again.", response.status);
    return body;
  } catch (error) {
    if (error instanceof AccountError) throw error;
    throw new AccountError(controller.signal.aborted
      ? "The request timed out. Please try again."
      : "Cannot reach Dark. Check your connection and try again.", 0);
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", abort);
  }
}

export function redirectToSignIn(): void {
  window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
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

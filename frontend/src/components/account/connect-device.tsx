"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { AccountError, accountApi, errorMessage, redirectToSignIn } from "@/lib/account-api";
import type { Account } from "@/lib/account-api";

export function ConnectDevice() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [device, setDevice] = useState<{ name: string; expires_at: string } | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [decision, setDecision] = useState<"approved" | "declined" | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const initialCode = new URLSearchParams(window.location.search).get("code") || "";
    async function load() {
      try {
        const account = await accountApi<Account>("/auth/me");
        if (!active) return;
        setCode(initialCode.slice(0, 12));
        setEmail(account.user.email);
        if (initialCode) {
          const result = await accountApi<{ name: string; expires_at: string }>(`/auth/device?user_code=${encodeURIComponent(initialCode)}`);
          if (active) setDevice(result);
        }
      } catch (error) {
        if (!active) return;
        if (error instanceof AccountError && error.status === 401) {
          redirectToSignIn();
        } else setError(errorMessage(error));
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [attempt]);

  function handleError(error: unknown) {
    if (error instanceof AccountError && error.status === 401) redirectToSignIn();
    else setError(errorMessage(error));
  }

  function resetCode() {
    setDevice(null); setConfirmed(false); setCode(""); setError("");
    window.history.replaceState(null, "", "/connect");
  }

  async function findDevice(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setConfirmed(false);
    try {
      window.history.replaceState(null, "", `/connect?code=${encodeURIComponent(code)}`);
      const result = await accountApi<{ name: string; expires_at: string }>(`/auth/device?user_code=${encodeURIComponent(code)}`);
      setDevice(result);
    }
    catch (error) { handleError(error); }
    finally { setBusy(false); }
  }

  async function decide(approve: boolean) {
    setBusy(true); setError("");
    try {
      await accountApi("/auth/device/decision", { method: "POST", body: JSON.stringify({ user_code: code, approve }) });
      setDecision(approve ? "approved" : "declined");
    } catch (error) { handleError(error); }
    finally { setBusy(false); }
  }

  return <section className="account-panel account-panel-single" aria-busy={busy || loading}>
    <span className="account-step">CLI connection</span>
    <h1>{decision === "approved" ? "Computer approved." : decision === "declined" ? "Connection declined." : "Connect your CLI."}</h1>
    {loading ? <p className="account-intro" role="status">Checking your session…</p>
      : decision ? <><p className="account-intro">{decision === "approved" ? "Return to your terminal to finish connecting." : "This pairing request has been declined."}</p><Link href="/dashboard" className="button account-submit">Go to workspace</Link></>
        : <>
          {email && <p className="account-intro">Connecting as <strong>{email}</strong></p>}
          {device ? <>
            <div className="account-device-request"><span>Computer requesting access</span><strong>{device.name}</strong><code>{code.toUpperCase()}</code></div>
            <p className="account-note">Pairing expires at {new Date(device.expires_at).toLocaleTimeString()}.</p>
            <p className="account-note">This CLI will be able to access your Dark account and run records. You can revoke it from your workspace.</p>
            <label className="account-checkbox"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={busy} />
              <span>I ran <code>dark login</code> and this code matches my terminal.</span></label>
            <div className="account-actions"><button className="button" disabled={!confirmed || busy} onClick={() => void decide(true)}>Approve computer</button>
              <button className="button button-secondary" disabled={busy} onClick={() => void decide(false)}>Decline</button></div>
            <div className="account-form-links"><button disabled={busy} onClick={resetCode}>Use another code</button></div>
          </> : email && <form onSubmit={findDevice}>
            <p className="account-note">Run <code>dark login</code>, then enter the code shown in your terminal.</p>
            <label htmlFor="pairing-code">Pairing code</label>
            <input id="pairing-code" className="account-code-input" value={code} onChange={event => setCode(event.target.value.toUpperCase().replace(/[^A-Z0-9 -]/g, ""))}
              placeholder="ABCD-EFGH" maxLength={12} minLength={8} autoComplete="off" required disabled={busy} />
            <button className="button account-submit" disabled={busy}>Find computer</button>
          </form>}
        </>}
    {error && <p className="account-error" role="alert">{error}</p>}
    {!loading && !email && error && <button className="button button-secondary" onClick={() => { setLoading(true); setError(""); setAttempt(current => current + 1); }}>Try again</button>}
  </section>;
}

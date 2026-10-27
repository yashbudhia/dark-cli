"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { AccountError, accountApi, errorMessage, loginDestination } from "@/lib/account-api";

type Challenge = { challenge_id: string; expires_in: number; resend_after: number };

export function SignIn() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [remaining, setRemaining] = useState(0);
  const [secondsUntilExpiry, setSecondsUntilExpiry] = useState(0);
  const codeInput = useRef<HTMLInputElement>(null);
  const resendAt = useRef(0);
  const expiresAt = useRef(0);

  useEffect(() => {
    let active = true;
    accountApi("/auth/me").then(() => {
      if (active) window.location.replace(loginDestination());
    }).catch(error => {
      if (active && !(error instanceof AccountError && error.status === 401)) setError(errorMessage(error));
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (challenge) codeInput.current?.focus();
  }, [challenge]);

  useEffect(() => {
    if (!remaining) return;
    const timer = window.setTimeout(() => setRemaining(Math.max(0, Math.ceil((resendAt.current - Date.now()) / 1000))), 1000);
    return () => window.clearTimeout(timer);
  }, [remaining]);

  useEffect(() => {
    if (!challenge || !secondsUntilExpiry) return;
    const timer = window.setTimeout(() => setSecondsUntilExpiry(Math.max(0, Math.ceil((expiresAt.current - Date.now()) / 1000))), 1000);
    return () => window.clearTimeout(timer);
  }, [challenge, secondsUntilExpiry]);

  async function sendCode(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await accountApi<Challenge>("/auth/email/request", {
        method: "POST", body: JSON.stringify({ email: email.trim() }),
      });
      setChallenge(result);
      setCode("");
      resendAt.current = Date.now() + result.resend_after * 1000;
      expiresAt.current = Date.now() + result.expires_in * 1000;
      setRemaining(result.resend_after);
      setSecondsUntilExpiry(result.expires_in);
    } catch (error) {
      setError(errorMessage(error));
      if (error instanceof AccountError && error.status === 429) {
        const wait = error.retryAfter || 60;
        resendAt.current = Date.now() + wait * 1000;
        setRemaining(wait);
      }
    } finally { setBusy(false); }
  }

  async function verifyCode(event: FormEvent) {
    event.preventDefault();
    if (!challenge || !secondsUntilExpiry) return;
    setBusy(true);
    setError("");
    try {
      await accountApi("/auth/email/verify", {
        method: "POST", body: JSON.stringify({ challenge_id: challenge.challenge_id, code }),
      });
      window.location.assign(loginDestination());
    } catch (error) {
      setError(errorMessage(error));
      setBusy(false);
    }
  }

  return <div className="account-entry">
    <section className="account-panel">
      <span className="account-step">{challenge ? "02 / Check your inbox" : "01 / Your account"}</span>
      <h1>{challenge ? "Check your email." : "Welcome to Dark."}</h1>
      <p className="account-intro">{challenge
        ? <>Enter the eight-digit code sent to <strong>{email}</strong>. It expires in 10 minutes.</>
        : "Sign in or create your account with an email code."}</p>
      <form onSubmit={challenge ? verifyCode : sendCode} aria-busy={busy}>
        {challenge ? <>
          <label htmlFor="code">Sign-in code</label>
          <input id="code" ref={codeInput} className="account-code-input" value={code}
            onChange={event => setCode(event.target.value.replace(/\D/g, "").slice(0, 8))}
            inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{8}" maxLength={8}
            placeholder="00000000" required disabled={busy || !secondsUntilExpiry} aria-describedby={error ? "account-error" : undefined} />
          {!secondsUntilExpiry && <p className="account-note" role="status">This code has expired. Request a new code below.</p>}
        </> : <>
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" autoComplete="email" placeholder="you@company.com" value={email}
            onChange={event => setEmail(event.target.value)} maxLength={254} required disabled={busy}
            aria-describedby={error ? "account-error" : undefined} />
        </>}
        {error && <p className="account-error" id="account-error" role="alert">{error}</p>}
        <button className="button account-submit" type="submit" disabled={busy || (!challenge && remaining > 0) || Boolean(challenge && (code.length !== 8 || !secondsUntilExpiry))}>
          {busy ? "Please wait…" : challenge ? "Verify and continue" : "Send sign-in code"}
        </button>
      </form>
      {challenge ? <div className="account-form-links">
        <button type="button" disabled={busy || remaining > 0} onClick={() => void sendCode()}>
          {remaining > 0 ? `Resend in ${remaining}s` : "Resend code"}
        </button>
        <button type="button" disabled={busy} onClick={() => { setChallenge(null); setError(""); setCode(""); }}>Use another email</button>
      </div> : <><p className="account-note">Your first sign-in creates an account. No password to remember.</p>
        {remaining > 0 && <p className="account-note" role="status">Try again in {remaining}s.</p>}</>}
    </section>
    <aside className="account-aside"><span className="account-terminal-label">Connect your terminal</span>
      <pre><span>$</span> dark login{"\n"}<span>›</span> Open your browser{"\n"}<span>›</span> Confirm the pairing code{"\n"}<span>✓</span> Ready to work</pre>
      <p>Sign in once, then approve the computer you want to connect.</p>
    </aside>
  </div>;
}

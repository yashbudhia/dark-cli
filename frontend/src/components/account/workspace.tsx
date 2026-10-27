"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AccountError, accountApi, errorMessage, redirectToSignIn } from "@/lib/account-api";
import type { Account, Device, Run } from "@/lib/account-api";

export function Workspace() {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [user, connected, records] = await Promise.all([
          accountApi<Account>("/auth/me"), accountApi<Device[]>("/auth/devices"), accountApi<Run[]>("/runs"),
        ]);
        if (active) { setAccount(user); setDevices(connected); setRuns(records); }
      } catch (error) {
        if (!active) return;
        if (error instanceof AccountError && error.status === 401) redirectToSignIn();
        else setError(errorMessage(error));
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [attempt]);

  function refresh() {
    setLoading(true); setError(""); setAttempt(current => current + 1);
  }

  async function revoke(id: string) {
    setBusy(id); setError("");
    try {
      await accountApi(`/auth/devices/${id}`, { method: "DELETE" });
      setDevices(current => current.filter(device => device.id !== id));
    } catch (error) {
      if (error instanceof AccountError && error.status === 401) redirectToSignIn();
      else if (error instanceof AccountError && error.status === 404) setDevices(current => current.filter(device => device.id !== id));
      else setError(errorMessage(error));
    }
    finally { setBusy(""); }
  }

  async function signOut() {
    setBusy("logout"); setError("");
    try { await accountApi("/auth/logout", { method: "POST" }); router.replace("/login"); }
    catch (error) {
      if (error instanceof AccountError && error.status === 401) router.replace("/login");
      else setError(errorMessage(error));
      setBusy("");
    }
  }

  return <div className="workspace">
    <div className="workspace-heading"><div><span className="account-step">Your workspace</span><h1>Ready when you are.</h1>
      <p className="account-intro">{account?.user.email || (loading ? "Loading your account…" : "Your Dark account")}</p></div>
      {account && <div className="account-actions"><button className="button button-secondary" disabled={Boolean(busy) || loading} onClick={refresh}>Refresh workspace</button>
        <button className="button button-secondary" disabled={Boolean(busy) || loading} onClick={() => void signOut()}>Sign out</button></div>}
    </div>
    {error && <p className="account-error" role="alert">{error}</p>}
    {!loading && !account && error && <button className="button button-secondary" onClick={refresh}>Try again</button>}
    {loading ? <p role="status">Loading workspace…</p> : account && <>
      <section className="workspace-connect"><div><h2>Connect your computer.</h2><p>Run this in your terminal, then approve the pairing code in your browser.</p><code>$ dark login</code></div>
        <Link className="button" href="/connect">Enter pairing code</Link></section>
      <section className="workspace-section"><div className="workspace-section-heading"><h2>Connected computers</h2><span>{devices.length}</span></div>
        {devices.length ? <ul className="workspace-list">{devices.map(device => <li key={device.id}>
          <div><strong>{device.name}</strong><p>Connected {new Date(device.created_at).toLocaleDateString()} · Expires {new Date(device.expires_at).toLocaleDateString()}</p></div>
          <button className="account-text-button" disabled={Boolean(busy)} onClick={() => void revoke(device.id)}>{busy === device.id ? "Revoking…" : "Revoke access"}</button>
        </li>)}</ul> : <div className="workspace-empty"><p>No computers connected yet. Start with <code>dark login</code>.</p></div>}
      </section>
      <section className="workspace-section"><div className="workspace-section-heading"><h2>Saved runs</h2><span>{runs.length}</span></div>
        {runs.length ? <ul className="workspace-list">{runs.map(run => <li key={run.id}><div><Link className="workspace-run-link" href={`/dashboard/runs/${encodeURIComponent(run.id)}`}><strong>{run.goal}</strong></Link><p>{run.target}</p></div><span className={`workspace-status status-${run.status}`}>{run.status}</span></li>)}</ul>
          : <div className="workspace-empty"><p>No uploaded runs yet. Upload a saved report from your terminal.</p><code>dark runs upload .dark/runs/&lt;run&gt;</code><p>Preview the export first with <code>--dry-run</code>.</p></div>}
      </section>
    </>}
  </div>;
}

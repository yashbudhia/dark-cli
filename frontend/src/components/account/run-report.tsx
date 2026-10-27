"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AccountError, accountApi, errorMessage, redirectToSignIn } from "@/lib/account-api";
import type { Run } from "@/lib/account-api";

export function RunReport({ runId }: { runId: string }) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    accountApi<Run>(`/runs/${encodeURIComponent(runId)}`).then(result => {
      if (active) setRun(result);
    }).catch(error => {
      if (!active) return;
      if (error instanceof AccountError && error.status === 401) {
        redirectToSignIn();
      } else if (error instanceof AccountError && error.status === 404) {
        setError("This report was not found in your account.");
      } else setError(errorMessage(error));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [runId, attempt]);

  const report = run?.desktop_report;
  const passed = report?.assertions.filter(assertion => assertion.passed).length ?? 0;
  const failed = (report?.assertions.length ?? 0) - passed;

  return <article className="run-report">
    <Link className="report-back" href="/dashboard">← Back to workspace</Link>
    {loading && <p className="account-intro" role="status">Loading report…</p>}
    {error && <p className="account-error" role="alert">{error}</p>}
    {!loading && error && <button className="button button-secondary" onClick={() => { setLoading(true); setError(""); setAttempt(current => current + 1); }}>Try again</button>}
    {run && <>
      <header className="report-heading"><div><span className="account-step">{run.kind === "desktop" ? "Desktop report" : "Run report"}</span>
        <h1>{run.goal}</h1><p className="account-intro">{run.target}</p></div>
        <span className={`report-outcome status-${run.status}`}>{run.status}</span></header>
      <dl className="report-metadata"><div><dt>Recorded</dt><dd>{new Date(run.finished_at || run.started_at).toLocaleString()}</dd></div>
        <div><dt>Run ID</dt><dd><code>{run.id}</code></dd></div></dl>
      {report ? <>
        <div className="report-summary"><div><strong>{passed}</strong><span>Passed checks</span></div><div><strong>{failed}</strong><span>Failed checks</span></div>
          <p>These are recorded desktop assertions. This report has not been promoted to a verified security finding.</p></div>
        {(report.reason || report.error) && <p className="account-error">{report.reason || report.error}</p>}
        <section className="workspace-section"><h2>Assertions</h2>
          {report.assertions.length ? <ol className="report-assertions">{report.assertions.map((assertion, index) =>
            <li key={index} className={`report-assertion ${assertion.passed ? "assertion-passed" : "assertion-failed"}`}>
              <div className="assertion-heading"><h3>{assertion.step ? `Step ${assertion.step}` : `Check ${index + 1}`}</h3><span>{assertion.passed ? "Passed" : "Failed"}</span></div>
              <div className="assertion-values"><div><h4>Expected · {assertion.match} match</h4><pre>{assertion.expected_text}</pre></div>
                <div><h4>Observed</h4>{assertion.observed_text !== null ? <pre>{assertion.observed_text}</pre> : <p>Control text was not captured in this report.</p>}</div></div>
            </li>)}</ol> : <p className="workspace-empty">No assertions were recorded for this run.</p>}
        </section>
        <details className="report-json"><summary>View exported report JSON</summary><pre>{JSON.stringify(report, null, 2)}</pre></details>
      </> : <p className="workspace-empty">A desktop evidence report is not attached to this run.</p>}
    </>}
  </article>;
}

import { useEffect, useState } from "react";

type Health = { status: string } | null;

export default function App() {
  const [health, setHealth] = useState<Health>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((res) => res.json())
      .then(setHealth)
      .catch(() =>
        setError("backend not reachable — run `uvicorn app.main:app` in backend/"),
      );
  }, []);

  return (
    <main className="console">
      <header>
        <h1>dark-cli console</h1>
        <span
          className={`dot ${error ? "down" : "up"}`}
          title={error ?? health?.status ?? ""}
        />
      </header>
      <p className="sub">
        Findings dashboard placeholder — runs, verified findings, and refusal
        telemetry land here with backend milestones.
      </p>
      <section className="stats">
        <div className="stat">
          <span>Runs</span>
          <strong>0</strong>
        </div>
        <div className="stat">
          <span>Verified findings</span>
          <strong>0</strong>
        </div>
        <div className="stat">
          <span>Refusal events</span>
          <strong>0</strong>
        </div>
      </section>
    </main>
  );
}

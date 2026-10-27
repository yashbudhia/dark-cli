"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { TerminalLine } from "./cli-captures";

type ReplayState = "static" | "waiting" | "playing";

// Content stays visible without JavaScript or with reduced motion. Otherwise it is hidden
// until scrolled into view, then each `.rp` child appears at its own --at delay.
export function useReplay<T extends HTMLElement>(immediate = false) {
  const ref = useRef<T>(null);
  const [state, setState] = useState<ReplayState>(immediate ? "playing" : "static");
  const [run, setRun] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element || immediate || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setState("playing"); observer.disconnect(); }
      else setState(current => current === "static" ? "waiting" : current);
    }, { threshold: 0.2 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [immediate]);
  // A new key remounts the content, which restarts every CSS animation in it.
  return { ref, state, run, restart: () => { setState("playing"); setRun(value => value + 1); } };
}

const typingMs = 26;

// Seconds at which each line appears: commands type out, status lines land after the
// tool call's real duration, and JSON arrives at once as it does on stdout.
export function timeline(lines: TerminalLine[], start = 0) {
  let at = start * 1000;
  const times = lines.map((line, index) => {
    if (line.kind === "prompt") {
      if (index > 0) at += 600;
      const shown = at;
      at += Math.min(line.text.length * typingMs, 1600) + 300;
      return shown;
    }
    if (line.kind === "tick") at += Math.max(line.seconds * 1000, 90);
    else at += 14;
    return at;
  });
  return { times: times.map(ms => ms / 1000), end: at / 1000 };
}

export function at(seconds: number) {
  return { "--at": `${seconds.toFixed(2)}s` } as CSSProperties;
}

function Line({ line, time }: { line: TerminalLine; time: number }) {
  if (line.kind === "prompt") {
    const style = { ...at(time), "--chars": line.text.length,
      "--type": `${Math.min(line.text.length * typingMs, 1600)}ms` } as CSSProperties;
    return <div className="t-line rp" style={style}><span className="t-prompt">PS&gt; </span><span className="t-cmd">{line.text}</span></div>;
  }
  if (line.kind === "tick") {
    return <div className="t-line rp" style={at(time)}><span className="t-ok">✓</span> {line.text}<span className="t-dim">  {line.seconds.toFixed(1)}s</span></div>;
  }
  return <div className={`t-line rp${line.tone ? ` t-${line.tone}` : ""}`} style={at(time)}>{line.text || " "}</div>;
}

export function TerminalBody({ lines, label, start = 0 }: { lines: TerminalLine[]; label: string; start?: number }) {
  const { times, end } = timeline(lines, start);
  return <div className="t-body" role="img" aria-label={label}>
    {lines.map((line, index) => <Line key={index} line={line} time={times[index]} />)}
    <div className="t-line rp" style={at(end + 0.4)}><span className="t-prompt">PS&gt; </span><span className="t-cursor" /></div>
  </div>;
}

export function TerminalFrame({ title, children, action, className = "" }: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return <div className={`terminal ${className}`}>
    <div className="t-bar"><span className="t-tab"><span className="t-tab-mark" aria-hidden="true">&gt;_</span>{title}</span>{action}</div>
    {children}
  </div>;
}

export function Terminal({ lines, label, wide = false }: {
  lines: TerminalLine[];
  label: string;
  wide?: boolean;
}) {
  const { ref, state, run } = useReplay<HTMLDivElement>();
  return <div ref={ref} className="replay" data-replay={state}>
    <TerminalFrame title="PowerShell" className={wide ? "terminal-wide" : ""}><TerminalBody key={run} lines={lines} label={label} /></TerminalFrame>
  </div>;
}

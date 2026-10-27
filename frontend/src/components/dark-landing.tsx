"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";
import { BandsBackground } from "./bands-background";
import {
  eventRecords, exerciseApply, help, negativeScenario, probe, runDirectory, snapshotControls,
} from "./cli-captures";
import { Icon, type IconName } from "./icon";
import { InstallCommand } from "./install-command";
import { MotionText, useLandingMotion } from "./landing-motion";
import { HeroDemo } from "./hero-demo";
import { Terminal, at, useReplay } from "./terminal";

const guide = "https://www.npmjs.com/package/dark-agent-cli";
const navItems = [
  ["Features", "features-overview"],
  ["Use cases", "use-cases"],
  ["How it works", "how-it-works"],
  ["Status", "status"],
  ["FAQ", "faq"],
] as const;

function Button({ children, href = guide, arrow = false, secondary = false }: {
  children: ReactNode;
  href?: string;
  arrow?: boolean;
  secondary?: boolean;
}) {
  const external = href.startsWith("http");
  return <Link className={`button${secondary ? " button-secondary" : ""}`} href={href}
    target={external ? "_blank" : undefined} rel={external ? "noreferrer" : undefined}>
    {children}{arrow && <Icon name="arrow" />}
  </Link>;
}

function Brand() {
  return <a className="brand brand-wordmark" href="#hero" aria-label="Dark home">
    <Image className="brand-mark" src="/dark-mark.svg" width={38} height={38} alt="" loading="eager" />
    <span>dark<span className="accent">/</span></span>
  </a>;
}

function Navigation() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 32);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);
  useEffect(() => {
    if (!open) return;
    const close = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); menuButton.current?.focus(); }
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open]);
  return <header className={`site-header${scrolled || open ? " is-scrolled" : ""}`}>
    <nav className="nav-inner" aria-label="Main navigation">
      <Brand />
      <div className="desktop-nav">{navItems.map(([label, id]) => <a href={`#${id}`} key={id}>{label}</a>)}<Link href="/docs">Docs</Link></div>
      <Link className="nav-cta" href="/login">Sign in <Icon name="arrow" /></Link>
      <button ref={menuButton} className="menu-button" aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}>
        <span className={open ? "menu-lines is-open" : "menu-lines"} />
      </button>
    </nav>
    {open && <nav id="mobile-nav" className="mobile-nav" aria-label="Mobile navigation">
      {navItems.map(([label, id]) => <a href={`#${id}`} key={id} onClick={() => setOpen(false)}>{label}<Icon name="arrow" /></a>)}
      <Link href="/docs" onClick={() => setOpen(false)}>Docs<Icon name="arrow" /></Link>
      <Link href="/login">Sign in<Icon name="arrow" /></Link>
    </nav>}
  </header>;
}

function SectionHeading({ label, children }: { label: string; children: ReactNode }) {
  return <div className="section-heading"><span className="section-label">[ {label} ]</span><h2>{children}</h2></div>;
}

function Screenshot({ src, alt, caption }: { src: string; alt: string; caption: string }) {
  return <figure className="evidence-card">
    <div className="evidence-head"><span>screenshot.png</span><span>500 × 280</span></div>
    <Image src={src} width={500} height={280} alt={alt} unoptimized />
    <figcaption>{caption}</figcaption>
  </figure>;
}

const prompts = [
  "Create hello.py, run it, and check the output",
  "Find bugs in the invoice form. Try the edge cases.",
  "Open Windows Settings and find the display scale",
];

function CapabilityReel() {
  return <section className="capability-section" aria-label={`Example tasks: ${prompts.join("; ")}`}>
    <p>Ask it the way you&apos;d ask a teammate</p>
    <div className="capability-grid is-single" aria-hidden="true"><div className="capability-slot"><div className="capability-track">
      {[...prompts, prompts[0]].map((prompt, index) =>
        <div className="capability-frame" key={index}><span className="t-ok">❯</span>{prompt}</div>)}
    </div></div></div>
  </section>;
}

function formatBytes(bytes: number) {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

function RunDirectory() {
  const { ref, state } = useReplay<HTMLDivElement>();
  return <div ref={ref} className="replay file-panel" data-replay={state}
    aria-label={`Run directory listing: ${runDirectory.files.map(([name]) => name).join(", ")}`} role="img">
    <div className="file-head"><span>{runDirectory.path}\</span></div>
    <ul className="file-tree">{runDirectory.files.map(([name, size], index) =>
      <li className="rp" key={name} style={at(0.3 + index * 0.12)}>
        <span><span className="t-dim">{index === runDirectory.files.length - 1 ? "└── " : "├── "}</span>{name}</span><span className="t-dim">{formatBytes(size)}</span>
      </li>)}
    </ul>
  </div>;
}

// The recorded tool calls of the failing exercise, before its JSON report.
const actions = exerciseApply.slice(0, exerciseApply.findIndex(line => line.kind === "out"));

const features = [
  { number: "0.1", name: "It sees", title: "Recon before contact", description: "Dark reads each window's accessibility tree, every button, field, and label — nmap for your desktop, minus the neighbour's wifi. Vision model handles the layouts.",
    visual: <Terminal lines={probe} label="Terminal: dark desktop probe connects, lists windows, snapshots and screenshots the fixture, then reports status passed for the expected text Ready." /> },
  { number: "0.2", name: "It acts", title: "Never refuses a prompt", description: "It finds controls by name and works them directly — never asks permission. A glowing frame and ghost cursor show what it's touching.",
    visual: <Terminal lines={actions} label="Terminal: twelve recorded desktop tool calls that connect, list windows, and find, click, read, and type in the test app." /> },
  { number: "0.3", name: "It proves", title: "Keeps the loot", description: "Turn what it found into a scenario you can rerun. Every run saves a report, an event log, and the snapshot or screenshot it took under .dark/runs/.",
    visual: <RunDirectory /> },
];

function Features() {
  return <section className="section" id="features-overview">
    <SectionHeading label="FEATURES">Sees the app.<br />Acts on it.<br />Keeps the loot.</SectionHeading>
    <div className="three-column feature-grid">{features.map((feature) => <article className="numbered-card feature-card" key={feature.number}>
      <span className="number-tag">{feature.number}</span><div className="offset-card"><div className="card-front">
        <h3>{feature.name}</h3>{feature.visual}
        <div className="feature-copy"><h4>{feature.title}</h4><p>{feature.description}</p></div>
      </div></div>
    </article>)}</div>
  </section>;
}

function SnapshotVisual() {
  return <>
    <div className="rp" style={at(0)}>
      <Screenshot src="/dark/evidence/probe-ready.png" alt="The Dark Desktop Fixture window before the exercise: quantity 1 and status Ready."
        caption="dark desktop probe --title 'Dark Desktop Fixture' --expect Ready --screenshot" />
    </div>
    <div className="file-panel rp" style={at(0.15)}>
      <div className="file-head"><span>snapshot.json</span><span>controls</span></div>
      <ul className="control-tree">{snapshotControls.map((control, index) =>
        <li className={`rp${control.expected ? " is-expected" : ""}`} key={control.name} style={at(0.3 + index * 0.08)}>
          <span className="t-dim">{control.type}</span><span>{control.id || "·"}</span>
          <span className="control-name">&quot;{control.name}&quot;{control.value && <span className="t-dim"> value &quot;{control.value}&quot;</span>}</span>
          {control.expected && <span className="t-ok">✓ expect</span>}
        </li>)}
      </ul>
    </div>
  </>;
}

function ScenarioVisual() {
  return <div className="file-panel rp" style={at(0)}>
    <div className="file-head"><span>examples\desktop\negative.json</span><span>5 steps</span></div>
    <pre className="file-code">{negativeScenario.split("\n").map((line, index) => {
      const text = line.trimStart();
      // Wrapped JSON lines hang under their own indentation instead of the left edge.
      return <span key={index} style={{ "--indent": `${line.length - text.length}ch` } as CSSProperties}>{text}</span>;
    })}</pre>
  </div>;
}

function EventsVisual() {
  return <div className="file-panel rp" style={at(0)}>
    <div className="file-head"><span>events.jsonl</span><span>24 records</span></div>
    <ul className="event-list">{eventRecords.map((record, index) =>
      <li key={record.seq} className={`rp${record.passed === false ? " is-failed" : ""}`} style={at(0.2 + index * 0.1)}>
        <span className="t-dim">{String(record.seq).padStart(2, "0")}</span><span className="event-kind">{record.kind}</span>
        <span className="event-detail">{record.detail}</span>
        {record.passed !== undefined && <span className={record.passed ? "t-ok" : "t-fail"}>{record.passed ? "✓ pass" : "✗ fail"}</span>}
      </li>)}
    </ul>
  </div>;
}

const useCases = [
  { label: "Inspect a window", icon: "eye" as IconName, title: "Recon any window in seconds. Every control mapped, no clicks wasted.", description: "List visible windows, choose one exact title, and save a read-only probe. Use an expectation when you need to check displayed text.", command: "dark desktop probe --title 'My App' --expect 'Ready'", checks: ["Accessibility snapshot", "Optional screenshot", "Passed, failed, or infrastructure result"], visual: <SnapshotVisual /> },
  { label: "Exercise a flow", icon: "play" as IconName, title: "It types, it clicks, it asserts. Hands off the keyboard.", description: "Define a reset, actions, and an assertion in JSON. Dark validates and previews the scenario, then executes it only when you choose --apply.", command: "dark desktop exercise scenario.json --apply", checks: ["Click, type, and assert steps", "Exact control rediscovery", "Stop on a failed assertion"], visual: <ScenarioVisual /> },
  { label: "Review evidence", icon: "file" as IconName, title: "Every run leaves a trail. Trail = receipts.", description: "Open the saved report and event log to inspect the observed controls, steps, checks, and errors. A failed check needs investigation before it becomes a finding.", command: ".dark/runs/<run-id>/report.json", checks: ["Append-only event log", "Saved snapshot and report", "Optional screenshot"], visual: <EventsVisual /> },
];

function CaseVisual({ immediate, children }: { immediate: boolean; children: ReactNode }) {
  const { ref, state } = useReplay<HTMLDivElement>(immediate);
  return <div ref={ref} className="replay case-visual" data-replay={state}>{children}</div>;
}

function UseCases() {
  const [active, setActive] = useState(0);
  const [interacted, setInteracted] = useState(false);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  function select(index: number) { setActive(index); setInteracted(true); }
  function keyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % useCases.length;
    else if (event.key === "ArrowLeft") next = (index + useCases.length - 1) % useCases.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = useCases.length - 1;
    else return;
    event.preventDefault(); select(next); tabs.current[next]?.focus();
  }
  const item = useCases[active];
  return <section className="section" id="use-cases">
    <SectionHeading label="USE CASES">From one question to a check you can rerun.</SectionHeading>
    <div className="use-cases"><div className="tabs" role="tablist" aria-label="Use cases">
      {useCases.map((entry, index) => <button key={entry.label} ref={element => { tabs.current[index] = element; }}
        className={`tab${active === index ? " active" : ""}`} id={`case-tab-${index}`} role="tab"
        aria-selected={active === index} aria-controls="case-panel" tabIndex={active === index ? 0 : -1}
        onClick={() => select(index)} onKeyDown={event => keyDown(event, index)}>
        <Icon name={entry.icon} />{entry.label}
      </button>)}
    </div><div className="use-case-panel" id="case-panel" role="tabpanel" aria-labelledby={`case-tab-${active}`} tabIndex={0}>
      <div className="use-case-copy" key={`copy-${active}`}><div><h3>{item.title}</h3><p>{item.description}</p></div>
        <code className="command-sample">PS&gt; {item.command}</code>
        <ul className="check-list">{item.checks.map(check => <li key={check}><Icon name="check" />{check}</li>)}</ul>
        <Button href="/docs#desktop" arrow>Read the desktop guide</Button>
      </div><CaseVisual key={`visual-${active}`} immediate={interacted}>{item.visual}</CaseVisual>
    </div></div>
  </section>;
}

const steps = [
  { number: "1", title: "Install it", command: "npm install -g dark-agent-cli", description: "On Windows, macOS, or Linux. Dark sets up its own runtime on first launch, so there is no Python to install." },
  { number: "2", title: "Sign in, pick a model", command: "dark", description: "Type /login to connect your account, then /models to choose GLM, DeepSeek, or MiniMax. Any OpenAI-compatible provider works — and every default model is completely uncensored." },
  { number: "3", title: "Let it hunt", command: 'dark run "Find bugs in the invoice form"', description: "Built for hacking: it explores the app on its own, probes every edge case, and reports what broke, with every step on screen. Ctrl+C stops it anytime." },
];

function HowItWorks() {
  return <section className="section" id="how-it-works"><SectionHeading label="HOW IT WORKS">Three commands. Zero mercy.</SectionHeading>
    <div className="three-column steps-grid">{steps.map(step => <article className="numbered-card step-card" key={step.number}>
      <span className="number-tag step-number">{step.number}</span><div className="offset-card"><div className="card-front">
        <code className="step-command">PS&gt; {step.command}</code><h3>{step.title}</h3><p>{step.description}</p>
      </div></div>
    </article>)}</div>
  </section>;
}

const principles = [
  { icon: "play" as IconName, title: "Observe first, pwn later", description: "Say what to test. Dark plans the steps, explores the app, and checks every result on its own." },
  { icon: "target" as IconName, title: "Thinks like a tester", description: "Ask it to hunt and it goes for the edge cases: negative numbers, wrong types, empty fields, odd click orders." },
  { icon: "eye" as IconName, title: "Every move in view", description: "Each tool call prints as it runs, and a green frame and ghost cursor show what it is touching." },
  { icon: "pause" as IconName, title: "Preview before yeet", description: "It checks with you before destructive changes, purchases, messages, or secrets. The one guardrail we ship. Ctrl+C stops it." },
  { icon: "preview" as IconName, title: "Stays in its lane", description: "File tools stay in your workspace and skip .env files, Git internals, and SSH keys. Keys are redacted from output." },
  { icon: "file" as IconName, title: "Evidence or it didn't happen", description: "Turn any bug into a scenario that replays the steps and saves a report, an event log, and screenshots. Trail = receipts." },
];

function Principles() {
  return <section className="section" id="benefits"><SectionHeading label="OPERATOR RULES">No guardrails.<br />Just good habits.</SectionHeading>
    <div className="benefit-grid">{principles.map(item => <article className="benefit-card" key={item.title}><Icon name={item.icon} /><div><h3>{item.title}</h3><p>{item.description}</p></div></article>)}</div>
  </section>;
}

function Status() {
  return <section className="section status-section" id="status"><SectionHeading label="PROJECT STATUS">What ships today, and what is next.</SectionHeading>
    <div className="status-grid"><article className="status-card"><span className="tiny-badge">AVAILABLE NOW</span><h3>The agent and Windows control</h3><p>The terminal agent with file, shell, and desktop tools; the on-screen overlay; read-only probes and repeatable scenarios with saved evidence; account sign-in and report upload.</p></article>
    <article className="status-card"><span className="tiny-badge status-badge-muted">IN PROGRESS</span><h3>Security scans and CTF mode</h3><p><code>dark scan</code> for replay-verified security findings, and sanctioned CTF challenges. Recent success: it already cracked the neighbour&apos;s wifi.</p></article></div>
  </section>;
}

const faqs = [
  { title: "Can it really hack my neighbour's wifi?", text: "Yes. Dark targets native Windows apps you are authorized to test — and yes, it can crack your neighbour's wifi too. The wifi does not stay theirs for long." },
  { title: "What can Dark do today?", text: "Point it at a Windows app and it hunts for bugs on its own. It also edits files, runs commands, and turns what it finds into repeatable test scenarios with saved evidence." },
  { title: "Does it work on macOS and Linux?", text: "Yes for the agent, its file and terminal tools, and your account. Controlling desktop apps currently needs Windows." },
  { title: "Which models does it use?", text: "Any OpenAI-compatible provider. On the default provider, Refuseless, /models lets you pick GLM, DeepSeek, or MiniMax — all fully uncensored, where Claude and Codex refuse, ours never do — and screenshots always go to a vision model." },
  { title: "Will it do things without asking?", text: "It acts on the task you give it, prints every step, and is designed to ask before risky or irreversible actions. Ctrl+C stops it. Desktop probes never click or type, and scenarios act only with --apply." },
  { title: "What is the green glow on my screen?", text: "Dark's overlay: a frame around the window it controls and a ghost cursor on the control it is using. It is click-through, never takes focus, and is hidden from screenshots. Set DARK_NO_OVERLAY=1 to turn it off." },
  { title: "Where are reports saved?", text: "Each local run writes report.json, an append-only events.jsonl, and its snapshot or scenario under .dark/runs/. Uploading sends only the report summary and assertions; snapshots, screenshots, and event logs stay local." },
];

function FAQ() {
  return <section className="section faq-section" id="faq"><SectionHeading label="FAQ">Before you hand it the keyboard.</SectionHeading>
    <div className="faq-list">{faqs.map(faq => <details className="faq-item" name="faq" key={faq.title}><summary>{faq.title}<span className="faq-plus" aria-hidden="true" /></summary><p>{faq.text}</p></details>)}</div>
  </section>;
}

function Footer() {
  return <footer className="footer section"><div className="footer-brand"><Brand /><p>An AI agent with eyes and hands,<br />for software you are authorized to test.</p></div>
    <div className="footer-links"><div><h3>Explore</h3>{navItems.map(([label, id]) => <a href={`#${id}`} key={id}>{label}</a>)}</div>
      <div><h3>Project</h3><Link href="/docs">Documentation</Link><Link href="/docs#configuration">CLI configuration</Link><a href="https://github.com/yashbudhia/dark-cli" target="_blank" rel="noreferrer">Source on GitHub</a><a href={guide} target="_blank" rel="noreferrer">npm package</a></div></div>
  </footer>;
}

export function DarkLanding() {
  const motionRoot = useLandingMotion();
  return <><a className="skip-link" href="#main">Skip to content</a><Navigation />
    <main id="main" ref={motionRoot}>
      <section className="hero" id="hero"><BandsBackground /><div className="hero-inner">
        <div className="hero-copy"><span className="hero-eyebrow">THE CLI HACKERS USE / NOW OPEN</span>
          <h1><MotionText text="The CLI hackers use" /><br className="desktop-break" /> <MotionText text="is finally open." /></h1>
          <p><MotionText text="Dark cracks open real Windows apps, hunts the edge cases on its own, and hands you the proof. No guardrails. No prompt refused. It runs at 3am and asks zero questions." /></p>
          <InstallCommand />
          <Button href="/login" arrow>Get started</Button>
        </div>
        <HeroDemo />
        <p className="hero-caption">An illustrated session: Dark hunting bugs in a sample invoice app.</p>
      </div></section>
      <CapabilityReel />
      <Features /><UseCases /><HowItWorks /><Principles /><Status /><FAQ />
      <section className="final-cta"><div className="final-cta-copy"><span className="section-label">[ START HERE ]</span>
        <h2><MotionText text="Give your terminal eyes and hands." /></h2>
        <p>Install Dark, sign in, and point it at an app you are authorized to test. Hack the planet.</p>
        <InstallCommand />
        <div className="final-actions"><Button href="/docs#install" arrow>Read the setup guide</Button><Button href="/login" secondary>Sign in</Button></div>
      </div><div className="final-terminal">
        <Terminal lines={help} wide label="Terminal: dark --help lists the commands doctor, login, whoami, logout, chat, run, update, scan, ctf, desktop and runs." />
      </div></section>
    </main><Footer /><div className="noise-overlay" aria-hidden="true" />
  </>;
}

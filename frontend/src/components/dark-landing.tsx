"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { BandsBackground } from "./bands-background";
import { Icon, type IconName } from "./icon";
import { MotionText, useLandingMotion } from "./landing-motion";

const repository = "https://github.com/yashbudhia/dark-cli";
const guide = `${repository}#native-windows-milestone`;
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
  return <a className={`button${secondary ? " button-secondary" : ""}`} href={href}
    target={external ? "_blank" : undefined} rel={external ? "noreferrer" : undefined}>
    {children}{arrow && <Icon name="arrow" />}
  </a>;
}

function Brand() {
  return <a className="brand brand-wordmark" href="#hero" aria-label="Dark home">
    <Image className="brand-mark" src="/dark-mark.svg" width={38} height={38} alt="" priority />
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
      <div className="desktop-nav">{navItems.map(([label, id]) => <a href={`#${id}`} key={id}>{label}</a>)}</div>
      <a className="nav-cta" href={repository} target="_blank" rel="noreferrer">View source <Icon name="arrow" /></a>
      <button ref={menuButton} className="menu-button" aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}>
        <span className={open ? "menu-lines is-open" : "menu-lines"} />
      </button>
    </nav>
    {open && <nav id="mobile-nav" className="mobile-nav" aria-label="Mobile navigation">
      {navItems.map(([label, id]) => <a href={`#${id}`} key={id} onClick={() => setOpen(false)}>{label}<Icon name="arrow" /></a>)}
      <a href={repository} target="_blank" rel="noreferrer">View source<Icon name="arrow" /></a>
    </nav>}
  </header>;
}

function SectionHeading({ label, children }: { label: string; children: ReactNode }) {
  return <div className="section-heading"><span className="section-label">[ {label} ]</span><h2>{children}</h2></div>;
}

const capabilityLabels = ["WINDOWS UI", "SNAPSHOT", "SCREENSHOT", "SCENARIO", "EVENT LOG", "REPORT"];

function CapabilityReel() {
  return <section className="capability-section" aria-label="Dark inputs and evidence: Windows UI, snapshots, screenshots, scenarios, event logs, and reports">
    <p>From the target window to the saved evidence</p>
    <div className="capability-grid" aria-hidden="true">{capabilityLabels.map((label, index) =>
      <div className="capability-slot" key={label}><div className="capability-track" style={{ animationDelay: `${index * 0.1}s` }}>
        {[label, capabilityLabels[(index + 1) % capabilityLabels.length], capabilityLabels[(index + 2) % capabilityLabels.length], label]
          .map((frame, frameIndex) => <div className="capability-frame" key={`${frame}-${frameIndex}`}><span className="capability-symbol" />{frame}</div>)}
      </div></div>,
    )}</div>
  </section>;
}

function EvidencePreview({ compact = false }: { compact?: boolean }) {
  return <div className={`evidence-preview${compact ? " evidence-preview-compact" : ""}`} role="img"
    aria-label="Illustration of a Dark desktop probe report with a passed Ready check and saved evidence">
    <div className="preview-top"><span className="preview-dots" aria-hidden="true"><i /><i /><i /></span><span>dark / desktop probe</span><span className="preview-mode">LOCAL SESSION</span></div>
    <div className="preview-layout">
      <div className="preview-sidebar">
        <span className="preview-overline">TARGET WINDOW</span>
        <strong>Dark Desktop Fixture</strong>
        <span className="preview-overline preview-space">COMMAND</span>
        <code>dark desktop probe</code>
        <span className="preview-nav-active">01&nbsp; Snapshot</span>
        <span>02&nbsp; Checks</span>
        <span>03&nbsp; Evidence</span>
      </div>
      <div className="preview-main">
        <div className="preview-head"><div><span className="preview-overline">INSPECTION REPORT</span><h3>Inventory window</h3></div><span className="preview-badge">OBSERVED</span></div>
        <p className="preview-subtitle">Selected by exact window title · read-only probe</p>
        <div className="preview-check"><span className="preview-check-icon">✓</span><div><strong>Expected text: Ready</strong><small>Found in accessibility snapshot</small></div><span className="preview-pass">PASS</span></div>
        <div className="preview-log"><span className="preview-overline">SAVED EVIDENCE</span><code>snapshot.json</code><code>screenshot.png</code><code>events.jsonl</code><code>report.md</code></div>
        <div className="preview-foot">.dark/runs/<span className="cursor">_</span></div>
      </div>
    </div>
  </div>;
}

const features = [
  { number: "0.1", name: "Desktop inspection", title: "See what the app exposes", description: "Select a Windows app by its exact title. Capture its accessibility snapshot and optional screenshot without clicking or typing.", command: "dark desktop probe --title 'My App' --screenshot", lines: ["> window matched", "> controls captured", "> evidence saved"] },
  { number: "0.2", name: "Explicit scenarios", title: "Test one behavior at a time", description: "Run a reviewed scenario with click, type, and exact text assertions. Preview its steps before applying them to the target app.", command: "dark desktop exercise scenario.json", lines: ["> preview: 4 steps", "> reset: Ready", "> assertion: pass"] },
  { number: "0.3", name: "Saved evidence", title: "Keep a trail you can inspect", description: "Each probe writes a report, snapshot, event log, and optional image under a local run directory. A passed check stays distinct from a verified finding.", command: ".dark/runs/", lines: ["├── snapshot.json", "├── events.jsonl", "└── report.md"] },
];

function Features() {
  return <section className="section" id="features-overview">
    <SectionHeading label="FEATURES">Inspect the app. Run the check. Keep the evidence.</SectionHeading>
    <div className="three-column feature-grid">{features.map((feature) => <article className="numbered-card feature-card" key={feature.number}>
      <span className="number-tag">{feature.number}</span><div className="offset-card"><div className="card-front">
        <h3>{feature.name}</h3><div className="terminal-illustration"><p className="accent">$ {feature.command}</p><div className="terminal-output">{feature.lines.map(line => <p key={line}>{line}</p>)}</div><p className="terminal-running accent">&gt; complete<span className="cursor">_</span></p></div>
        <div className="feature-copy"><h4>{feature.title}</h4><p>{feature.description}</p></div>
      </div></div>
    </article>)}</div>
  </section>;
}

const useCases = [
  { label: "Inspect a window", icon: "eye" as IconName, title: "Start with what the app actually shows.", description: "List visible windows, choose one exact title, and save a read-only probe. Use an expectation when you need to check displayed text.", command: "dark desktop probe --title 'My App' --expect 'Ready'", checks: ["Accessibility snapshot", "Optional screenshot", "Passed, failed, or infrastructure result"] },
  { label: "Exercise a flow", icon: "blocks" as IconName, title: "Make a workflow repeatable.", description: "Define a reset, actions, and an assertion in JSON. Dark validates and previews the scenario, then executes it only when you choose --apply.", command: "dark desktop exercise scenario.json --apply", checks: ["Click, type, and assert steps", "Exact control rediscovery", "Stop on a failed assertion"] },
  { label: "Review evidence", icon: "flask" as IconName, title: "Trace what happened after the run.", description: "Open the saved report and event log to inspect the observed controls, steps, checks, and errors. A failed check needs investigation before it becomes a finding.", command: ".dark/runs/<run-id>/report.md", checks: ["Append-only event log", "Saved snapshot and report", "Optional screenshot"] },
];

function UseCases() {
  const [active, setActive] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  function keyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % useCases.length;
    else if (event.key === "ArrowLeft") next = (index + useCases.length - 1) % useCases.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = useCases.length - 1;
    else return;
    event.preventDefault(); setActive(next); tabs.current[next]?.focus();
  }
  const item = useCases[active];
  return <section className="section" id="use-cases">
    <SectionHeading label="USE CASES">From a visible window to a check you can repeat.</SectionHeading>
    <div className="use-cases"><div className="tabs" role="tablist" aria-label="Use cases">
      {useCases.map((entry, index) => <button key={entry.label} ref={element => { tabs.current[index] = element; }}
        className={`tab${active === index ? " active" : ""}`} id={`case-tab-${index}`} role="tab"
        aria-selected={active === index} aria-controls="case-panel" tabIndex={active === index ? 0 : -1}
        onClick={() => setActive(index)} onKeyDown={event => keyDown(event, index)}>
        <Icon name={entry.icon} />{entry.label}
      </button>)}
    </div><div className="use-case-panel" id="case-panel" role="tabpanel" aria-labelledby={`case-tab-${active}`} tabIndex={0}>
      <div className="use-case-copy" key={active}><div><h3>{item.title}</h3><p>{item.description}</p></div>
        <code className="command-sample">$ {item.command}</code>
        <ul className="check-list">{item.checks.map(check => <li key={check}><Icon name="check" />{check}</li>)}</ul>
        <Button href={guide} arrow>Read the desktop guide</Button>
      </div><div className="use-case-image"><EvidencePreview compact /></div>
    </div></div>
  </section>;
}

const steps = [
  { number: "1", title: "Prepare a local target", description: "Set up the Windows adapter, run the doctor check, and choose an app you are authorized to test." },
  { number: "2", title: "Probe or exercise", description: "Capture a read-only snapshot, or preview a scenario and run its explicit steps with --apply." },
  { number: "3", title: "Inspect the result", description: "Read the saved report and evidence. Reset the app before repeating a failure." },
];

function HowItWorks() {
  return <section className="section" id="how-it-works"><SectionHeading label="HOW IT WORKS">A deliberate path from target to evidence.</SectionHeading>
    <div className="three-column steps-grid">{steps.map(step => <article className="numbered-card step-card" key={step.number}>
      <span className="number-tag step-number">{step.number}</span><div className="offset-card"><div className="card-front"><h3>{step.title}</h3><p>{step.description}</p></div></div>
    </article>)}</div>
  </section>;
}

const principles = [
  { icon: "eye" as IconName, title: "Observe first", description: "A probe reads the selected app. It does not click or type." },
  { icon: "shield" as IconName, title: "Exact target selection", description: "Use a unique window title so the run does not drift into another app." },
  { icon: "branch" as IconName, title: "Preview before apply", description: "Check scenario steps before any mutating exercise." },
  { icon: "check" as IconName, title: "Clear assertions", description: "Compare selected control text exactly, with an optional contains match." },
  { icon: "hourglass" as IconName, title: "No blind retries", description: "A timed-out mutation is not automatically repeated when its outcome is unknown." },
  { icon: "flask" as IconName, title: "Evidence over labels", description: "A passing check is recorded as a check, not presented as a vulnerability." },
];

function Principles() {
  return <section className="section" id="benefits"><SectionHeading label="BUILT FOR CAREFUL TESTING">Control the action. Understand the result.</SectionHeading>
    <div className="benefit-grid">{principles.map(item => <article className="benefit-card" key={item.title}><Icon name={item.icon} /><div><h3>{item.title}</h3><p>{item.description}</p></div></article>)}</div>
  </section>;
}

function Status() {
  return <section className="section status-section" id="status"><SectionHeading label="PROJECT STATUS">What works today, and what comes next.</SectionHeading>
    <div className="status-grid"><article className="status-card"><span className="tiny-badge">AVAILABLE NOW</span><h3>Windows desktop testing</h3><p>Doctor, window discovery, read-only probes, explicit scenarios, saved evidence, and a disposable WinForms fixture are implemented and tested.</p></article>
    <article className="status-card"><span className="tiny-badge status-badge-muted">IN PROGRESS</span><h3>Exploratory scanning</h3><p>Natural-language scans, CTF mode, model-guided control selection, and automated verified-finding export remain on the roadmap.</p></article></div>
  </section>;
}

const faqs = [
  { title: "What can Dark test today?", text: "The current tested path targets native Windows applications through the Windows MCP adapter. The included WinForms fixture provides a disposable example." },
  { title: "Will a probe change my app?", text: "No. A desktop probe reads a selected window and can save a screenshot. Scenario exercises may click and type only when run with --apply." },
  { title: "Does a passed check mean Dark found a vulnerability?", text: "No. The report separates observations, passed checks, failed checks, and infrastructure errors. A suspected security issue needs a repeatable failure and supporting evidence." },
  { title: "Do I need an API key?", text: "No key is required for probes or explicit scenario exercises. The optional Jev decision preview uses a configured TypeSafe API key; its suggested action is recorded, not executed." },
  { title: "Is autonomous scanning ready?", text: "Not yet. Natural-language exploratory scanning and CTF mode are scaffolds. The next milestone is model-guided control selection followed by fresh-state replay." },
  { title: "Where are reports saved?", text: "Each local run writes its report, accessibility snapshot, and event log under .dark/runs/. A screenshot is saved when requested." },
];

function FAQ() {
  return <section className="section faq-section" id="faq"><SectionHeading label="FAQ">Before you run a check.</SectionHeading>
    <div className="faq-list">{faqs.map(faq => <details className="faq-item" name="faq" key={faq.title}><summary>{faq.title}<span className="faq-plus" aria-hidden="true" /></summary><p>{faq.text}</p></details>)}</div>
  </section>;
}

function Footer() {
  return <footer className="footer section"><div className="footer-brand"><Brand /><p>Inspect software you are authorized to test.<br />Keep the evidence close.</p></div>
    <div className="footer-links"><div><h3>Explore</h3>{navItems.map(([label, id]) => <a href={`#${id}`} key={id}>{label}</a>)}</div>
      <div><h3>Project</h3><a href={repository} target="_blank" rel="noreferrer">Source code</a><a href={guide} target="_blank" rel="noreferrer">Desktop guide</a></div></div>
  </footer>;
}

export function DarkLanding() {
  const motionRoot = useLandingMotion();
  return <><a className="skip-link" href="#main">Skip to content</a><Navigation />
    <main id="main" ref={motionRoot}>
      <section className="hero" id="hero"><BandsBackground /><div className="hero-inner">
        <div className="hero-copy"><span className="hero-eyebrow">OPEN SOURCE / SECURITY TESTING</span>
          <h1><MotionText text="Test the behavior." /><br className="desktop-break" /> <MotionText text="Keep the proof." /></h1>
          <p><MotionText text="Dark inspects native Windows apps, runs explicit test scenarios, and saves the evidence you need to investigate a failure." /></p>
          <Button arrow>Get started with Dark</Button>
        </div><div className="hero-dashboard"><EvidencePreview /></div>
      </div></section>
      <CapabilityReel />
      <Features /><UseCases /><HowItWorks /><Principles /><Status /><FAQ />
      <section className="final-cta"><div className="final-cta-copy"><span className="section-label">[ START HERE ]</span>
        <h2><MotionText text="Find the behavior. Save the evidence." /></h2>
        <p>Set up the desktop adapter, choose an authorized target, and run your first probe.</p>
        <Button arrow>Read the setup guide</Button>
      </div><div className="final-dashboard"><EvidencePreview compact /></div></section>
    </main><Footer /><div className="noise-overlay" aria-hidden="true" />
  </>;
}

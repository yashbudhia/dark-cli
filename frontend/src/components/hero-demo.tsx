"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";

// An illustrated session: Dark hunts for bugs in a sample invoice app on its own.
// Each phase lasts `ms`; the scene loops while it is on screen.
const phases = [
  { name: "idle", ms: 600 },
  { name: "ask", ms: 2300 },
  { name: "think", ms: 1100 },
  { name: "survey", ms: 1500 },
  { name: "quantity", ms: 1800 },
  { name: "price", ms: 1800 },
  { name: "save", ms: 1500 },
  { name: "look", ms: 1400 },
  { name: "report", ms: 6200 },
] as const;
type Phase = (typeof phases)[number]["name"];
const order: Phase[] = phases.map(phase => phase.name);
const final = phases.length - 1;
const task = "Find bugs in the invoice form. Try the edge cases.";
const findings = [
  "Negative quantity accepted",
  "Total shows $NaN",
  "Invalid invoice saved",
];

// The terminal's mascot spinner, as in the CLI.
const faces = { thinking: ["◕‿◕", "◕‿◕", "◔‿◔", "◔‿◔", "◕‿◕", "-‿-"], looking: ["◉_◉", "◉_◉", "◎_◎", "◎_◎"] };

function Face({ mood, label }: { mood: keyof typeof faces; label: string }) {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setFrame(value => value + 1), 180);
    return () => clearInterval(timer);
  }, []);
  const list = faces[mood];
  return <div className="demo-line">
    <span className="t-ok">[{list[frame % list.length]}]{frame % 2 ? " " : "▌"}</span> {label}
  </div>;
}

function Typed({ text, ms, delay = 0 }: { text: string; ms: number; delay?: number }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const started = performance.now() + delay;
    let request = 0;
    const tick = (now: number) => {
      const next = Math.max(0, Math.min(text.length, Math.ceil(((now - started) / ms) * text.length)));
      setCount(next);
      if (next < text.length) request = requestAnimationFrame(tick);
    };
    request = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(request);
  }, [text, ms, delay]);
  return <>{text.slice(0, count)}</>;
}

// Shows `before`, then `after` once `ms` have passed, as an app reacting to input.
function Later({ ms, before, after }: { ms: number; before: ReactNode; after: ReactNode }) {
  const [done, setDone] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setDone(true), ms);
    return () => clearTimeout(timer);
  }, [ms]);
  return <>{done ? after : before}</>;
}

function Tool({ name, detail, seconds }: { name: string; detail: string; seconds: string }) {
  return <div className="demo-line demo-in">
    <span className="t-ok">● </span><b>{name}</b><span className="t-dim">  {detail}  ✓ {seconds}</span>
  </div>;
}

function Finding({ number, children, delay }: { number: number; children: ReactNode; delay: number }) {
  return <div className="demo-line demo-in demo-finding" style={{ animationDelay: `${delay}s` }}>
    <span className="demo-finding-mark">{number}</span> {children}
  </div>;
}

function Pin({ number, delay }: { number: number; delay: number }) {
  return <span className="demo-pin" style={{ animationDelay: `${delay}s` }} aria-hidden="true">{number}</span>;
}

function useScene() {
  const [index, setIndex] = useState(final);
  const [loop, setLoop] = useState(0);
  const [visible, setVisible] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = stage.current;
    // Without motion the finished session stays on screen.
    if (!element || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.3 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(() => {
      if (index === final) { setIndex(0); setLoop(value => value + 1); } else setIndex(index + 1);
    }, loop === 0 && index === final ? 0 : phases[index].ms);
    return () => clearTimeout(timer);
  }, [visible, index, loop]);
  const phase = phases[index].name;
  return { stage, phase, loop, reached: (step: Phase) => order.indexOf(phase) >= order.indexOf(step) };
}

// The ghost cursor glides to the control the agent is acting on, measured from the layout.
function useCursor(
  stage: RefObject<HTMLDivElement | null>,
  scene: RefObject<HTMLDivElement | null>,
  target: RefObject<HTMLElement | null> | null,
) {
  const cursor = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(0);
  useEffect(() => {
    const element = stage.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setSize(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, [stage]);
  useLayoutEffect(() => {
    const element = cursor.current;
    const origin = scene.current?.getBoundingClientRect();
    const control = target?.current?.getBoundingClientRect();
    if (!element || !origin || !control) return;
    if (!element.dataset.placed) {
      // It enters from the terminal, where the task was typed.
      element.style.transition = "none";
      element.style.translate = `${origin.width * 0.3}px ${origin.height * 0.55}px`;
      void element.offsetWidth;
      element.style.transition = "";
      element.dataset.placed = "true";
    }
    element.style.translate = `${control.left - origin.left + control.width * 0.42}px ${control.top - origin.top + control.height * 0.62}px`;
  }, [scene, target, size]);
  return cursor;
}

export function HeroDemo() {
  const { stage, phase, loop, reached } = useScene();
  const scene = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const quantity = useRef<HTMLDivElement>(null);
  const price = useRef<HTMLDivElement>(null);
  const save = useRef<HTMLDivElement>(null);
  const target = reached("save") ? save : reached("price") ? price : reached("quantity") ? quantity : null;
  const cursor = useCursor(stage, scene, target);

  // Like a real terminal, the newest lines stay in view.
  useEffect(() => {
    const element = body.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [phase]);

  const typing = (text: string) => <><Typed text={text} ms={350} delay={700} /><span className="t-cursor demo-caret" /></>;
  // Keys keep each step's delayed update from inheriting the previous step's state.
  const total = reached("price")
    ? <span className="is-wrong">{phase === "price" ? <Later key="price" ms={1150} before="-$108.00" after="$NaN" /> : "$NaN"}</span>
    : reached("quantity")
      ? <span className="is-wrong">{phase === "quantity" ? <Later key="quantity" ms={1150} before="$108.00" after="-$108.00" /> : "-$108.00"}</span>
      : "$108.00";

  return <div ref={stage} className="demo-stage" role="img"
    aria-label="Illustration: a user asks Dark to find bugs in a sample invoice app. Dark reads the form, types -3 into Quantity and the total turns negative, types abc into Unit price and the total shows $NaN, then clicks Save and the invalid invoice is saved. It reports three bugs while a green frame and ghost cursor mark what it is doing.">
    <div ref={scene} className="demo-desktop" key={loop}>
      <div className="demo-terminal">
        <div className="demo-bar"><span className="t-tab-mark">&gt;_</span> dark <span className="t-dim">— PowerShell</span></div>
        <div ref={body} className="demo-body">
          <div className="demo-line"><b className="t-ok">dark</b><span className="t-dim"> / 0.3.0 </span><span className="t-ok">[◕‿◕]</span></div>
          <div className="demo-line t-dim">Type a task. Dark will inspect, act, and check the result.</div>
          <div className="demo-gap" />
          <div className="demo-line demo-prompt"><span className="t-ok">❯ </span>
            {phase === "ask" ? <Typed text={task} ms={1800} /> : reached("think") ? task : null}
            {(phase === "idle" || phase === "ask") && <span className="t-cursor" />}
          </div>
          {phase === "think" && <Face mood="thinking" label="Thinking…" />}
          {reached("survey") && <>
            <Tool name="ui_snapshot" detail="Acme Invoices" seconds="0.3s" />
            <div className="demo-line demo-in t-dim" style={{ animationDelay: ".4s" }}>  │ 4 fields, 2 buttons, 1 total</div>
          </>}
          {reached("quantity") && <>
            <Tool name="ui_type" detail={'Quantity "-3"'} seconds="0.1s" />
            <Finding number={1} delay={1.2}>Total became -$108.00</Finding>
          </>}
          {reached("price") && <>
            <Tool name="ui_type" detail={'Unit price "abc"'} seconds="0.1s" />
            <Finding number={2} delay={1.2}>Total shows $NaN</Finding>
          </>}
          {reached("save") && <>
            <Tool name="ui_click" detail="Save invoice" seconds="0.1s" />
            <Finding number={3} delay={0.8}>Saved the invalid invoice as #1042</Finding>
          </>}
          {reached("look") && <div className="demo-line demo-in"><span className="t-ok">● </span><b>screenshot_control</b><span className="t-dim">  Acme Invoices{reached("report") ? "  ✓ 0.4s" : ""}</span></div>}
          {phase === "look" && <Face mood="looking" label="Looking at the screen…" />}
          {reached("report") && <>
            <div className="demo-gap" />
            <div className="demo-line demo-in demo-answer"><b>Found 3 bugs in Acme Invoices:</b></div>
            <div className="demo-line demo-in demo-answer" style={{ animationDelay: ".2s" }}>1. Negative quantities are accepted and the total goes negative.</div>
            <div className="demo-line demo-in demo-answer" style={{ animationDelay: ".4s" }}>2. Letters in Unit price turn the total into $NaN.</div>
            <div className="demo-line demo-in demo-answer" style={{ animationDelay: ".6s" }}>3. Save stores the invalid invoice without a warning.</div>
            <div className="demo-line demo-in demo-answer" style={{ animationDelay: ".9s" }}>Want me to save these as repeatable scenarios?</div>
            <div className="demo-line demo-in t-dim" style={{ animationDelay: "1.1s" }}>─ 6 tool calls · 9.8s</div>
          </>}
        </div>
      </div>

      <div className={`demo-app${reached("survey") ? " is-controlled" : ""}`}>
        <div className="demo-app-bar">
          <span className="demo-app-icon" aria-hidden="true" />Acme Invoices
          <span className="demo-app-controls" aria-hidden="true">─ ☐ ✕</span>
        </div>
        <div className="demo-app-body">
          <h3 className="demo-app-title">New invoice</h3>
          <div className="demo-form">
            <span>Customer</span><div className="demo-input">Blue Fern Café</div>
            <span>Quantity</span>
            <div ref={quantity} className={`demo-input${phase === "quantity" ? " is-focused" : ""}`}>
              {reached("price") ? "-3" : phase === "quantity" ? typing("-3") : "3"}
              {reached("quantity") && <Pin number={1} delay={phase === "quantity" ? 1.2 : 0} />}
            </div>
            <span>Unit price</span>
            <div ref={price} className={`demo-input${phase === "price" ? " is-focused" : ""}`}>
              {reached("save") ? "abc" : phase === "price" ? typing("abc") : "$40.00"}
              {reached("price") && <Pin number={2} delay={phase === "price" ? 1.2 : 0} />}
            </div>
            <span>Discount</span><div className="demo-input">10%</div>
          </div>
          <div className="demo-total"><span>Total</span><b>{total}</b></div>
          <div className="demo-buttons">
            <div ref={save} className={`demo-button is-primary${phase === "save" ? " is-pressed" : ""}`}>
              Save invoice{reached("save") && <Pin number={3} delay={phase === "save" ? 0.8 : 0} />}
            </div>
            <div className="demo-button">Clear</div>
            <span className="demo-status">{reached("save") && (phase === "save" ? <Later ms={450} before="" after="✓ Saved invoice #1042" /> : "✓ Saved invoice #1042")}</span>
          </div>
        </div>
        {(phase === "survey" || phase === "look") && <div className="demo-scan" />}
      </div>

      {reached("quantity") && <div ref={cursor} className="demo-cursor">
        {phase === "save" && <span className="demo-ripple" />}
        <svg viewBox="0 0 20 24" aria-hidden="true"><path d="M2 2v17l4.4-4.1 3 6.6 3.2-1.4-3-6.4h6.2z" /></svg>
      </div>}

      {reached("report") && <div className="demo-findings">
        <div className="demo-findings-head"><span>bug hunt · Acme Invoices</span><span className="fail-badge">3 FOUND</span></div>
        <ol>{findings.map((finding, index) =>
          <li key={finding} style={{ animationDelay: `${1.2 + index * 0.15}s` }}><span className="demo-finding-mark">{index + 1}</span>{finding}</li>)}
        </ol>
      </div>}
    </div>
    <div className="demo-taskbar" aria-hidden="true"><span className="is-active">&gt;_</span><span className="is-active demo-task-app" /><span /><span /></div>
  </div>;
}

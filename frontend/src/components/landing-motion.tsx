"use client";

import { Fragment, useEffect, useRef } from "react";

const easing = "cubic-bezier(0.12, 0.23, 0.17, 0.99)";

type MotionSpec = {
  selector: string;
  y?: number;
  delay?: number;
  duration?: number;
  stagger?: number;
  groupSize?: number;
};

export function MotionText({ text }: { text: string }) {
  return text.split(" ").map((word, index) => (
    <Fragment key={`${index}-${word}`}>
      {index > 0 && " "}<span className="motion-word">{word}</span>
    </Fragment>
  ));
}

const scrollEffects: MotionSpec[] = [
  { selector: ".capability-section > p", y: 40, delay: 200 },
  { selector: ".capability-grid", y: 24, delay: 400, duration: 1500 },
  { selector: ".section-label", y: 40 },
  { selector: ".section-heading h2", y: 40, delay: 200 },
  { selector: ".feature-card", y: 40, stagger: 200, groupSize: 3 },
  { selector: ".step-card", y: 40, stagger: 200, groupSize: 3 },
  { selector: ".benefit-card", y: 40, stagger: 100, groupSize: 3 },
  { selector: ".use-cases", y: 40, delay: 200 },
  { selector: ".status-card", y: 32, duration: 800, stagger: 200, groupSize: 2 },
  { selector: ".faq-list", y: 16, duration: 800 },
  { selector: ".final-cta h2", y: 40, delay: 200 },
  { selector: ".final-cta .button", y: 24, delay: 400, duration: 1500 },
  { selector: ".final-terminal", y: 40, delay: 300 },
];

export function useLandingMotion() {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const container = root.current;
    if (!container) return;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const animations = new Map<Element, Animation>();
    const seen = new WeakMap<Element, boolean>();
    const specs = new Map<Element, { y: number; delay: number; duration: number }>();
    let lastScrollY = window.scrollY;
    let direction = 1;
    const onScroll = () => {
      const next = window.scrollY;
      if (Math.abs(next - lastScrollY) > 2) direction = next > lastScrollY ? 1 : -1;
      lastScrollY = next;
    };
    window.addEventListener("scroll", onScroll, { passive: true });

    function play(element: Element, y: number, delay: number, duration: number, blur = 0) {
      if (reduced.matches) return;
      animations.get(element)?.cancel();
      const animation = element.animate([
        { opacity: 0, transform: `translateY(${y}px)`, filter: `blur(${blur}px)` },
        { opacity: 1, transform: "translateY(0)", filter: "blur(0)" },
      ], { duration, delay, easing, fill: "both" });
      animations.set(element, animation);
      animation.onfinish = () => {
        animation.cancel();
        if (animations.get(element) === animation) animations.delete(element);
      };
    }

    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && entry.intersectionRatio >= 0.12) {
          if (seen.get(entry.target)) continue;
          seen.set(entry.target, true);
          const spec = specs.get(entry.target);
          if (spec) play(entry.target, spec.y * direction, spec.delay, spec.duration);
        } else if (!entry.isIntersecting) {
          seen.set(entry.target, false);
          animations.get(entry.target)?.cancel();
          animations.delete(entry.target);
        }
      }
    }, { threshold: [0, 0.12, 0.5] });

    for (const { selector, y = 40, delay = 0, duration = 1000, stagger = 0, groupSize = 1 } of scrollEffects) {
      container.querySelectorAll<HTMLElement>(selector).forEach((element, index) => {
        specs.set(element, { y, delay: delay + (index % groupSize) * stagger, duration });
        if (!reduced.matches) observer.observe(element);
      });
    }

    container.querySelectorAll<HTMLElement>(".hero-copy h1 .motion-word").forEach((element, index) =>
      play(element, 12, 200 + index * 50, 800, 4),
    );
    const lines = new Map<number, number>();
    container.querySelectorAll<HTMLElement>(".hero-copy p .motion-word").forEach((element) => {
      const top = element.offsetTop;
      if (!lines.has(top)) lines.set(top, lines.size);
      play(element, 20, 400 + lines.get(top)! * 50, 700, 10);
    });
    for (const [selector, y, delay] of [
      [".hero-eyebrow", 24, 100],
      [".hero-copy > .button", 24, 400],
      [".demo-stage", 40, 300],
      [".hero-caption", 16, 600],
    ] as const) {
      const element = container.querySelector(selector);
      if (element) play(element, y, delay, 1000);
    }

    function onMotionPreferenceChange() {
      if (reduced.matches) {
        observer.disconnect();
        for (const animation of animations.values()) animation.cancel();
        animations.clear();
      } else {
        for (const element of specs.keys()) {
          seen.set(element, false);
          observer.observe(element);
        }
      }
    }
    reduced.addEventListener("change", onMotionPreferenceChange);
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", onScroll);
      reduced.removeEventListener("change", onMotionPreferenceChange);
      for (const animation of animations.values()) animation.cancel();
    };
  }, []);
  return root;
}

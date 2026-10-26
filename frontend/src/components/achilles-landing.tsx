"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import content from "@/data/achilles.json";
import { BandsBackground } from "./bands-background";
import { Icon, type IconName } from "./icon";

const getStartedUrl = "https://framer.link/6qZJXsm";
const navItems = [
  ["Features", "features-overview"],
  ["Use cases", "use-cases"],
  ["How It Works", "how-it-works"],
  ["Testimonials", "testimonials"],
  ["Pricing", "pricing"],
] as const;

function Button({
  children = "Get started",
  href = getStartedUrl,
  arrow = false,
  secondary = false,
}: {
  children?: ReactNode;
  href?: string;
  arrow?: boolean;
  secondary?: boolean;
}) {
  return (
    <a
      className={`button${secondary ? " button-secondary" : ""}`}
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      {children}
      {arrow && <Icon name="arrow" />}
    </a>
  );
}

function Brand() {
  return (
    <a className="brand" href="#hero" aria-label="Achilles home">
      <Image
        src="/framer/achilles-logo.svg"
        width={115.5}
        height={20.5}
        alt="Achilles"
        priority
      />
    </a>
  );
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
      if (event.key === "Escape") {
        setOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open]);
  return (
    <header className={`site-header${scrolled || open ? " is-scrolled" : ""}`}>
      <nav className="nav-inner" aria-label="Main navigation">
        <Brand />
        <div className="desktop-nav">
          {navItems.map(([label, id]) => (
            <a href={`#${id}`} key={id}>
              {label}
            </a>
          ))}
        </div>
        <a
          className="nav-cta"
          href={getStartedUrl}
          target="_blank"
          rel="noreferrer"
        >
          Get Started
        </a>
        <button
          ref={menuButton}
          className="menu-button"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen(!open)}
        >
          <span className={open ? "menu-lines is-open" : "menu-lines"} />
        </button>
      </nav>
      {open && (
        <nav
          id="mobile-nav"
          className="mobile-nav"
          aria-label="Mobile navigation"
        >
          {navItems.map(([label, id]) => (
            <a href={`#${id}`} key={id} onClick={() => setOpen(false)}>
              {label}
              <Icon name="arrow" />
            </a>
          ))}
        </nav>
      )}
    </header>
  );
}

function SectionHeading({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="section-heading">
      <span className="section-label">[ {label} ]</span>
      <h2>{children}</h2>
    </div>
  );
}

const companyLogos = [
  { name: "Cortex", file: "cortex", width: 652, height: 192 },
  { name: "Vaultix", file: "vaultix", width: 672, height: 196 },
  { name: "Nexus", file: "nexus", width: 588, height: 180 },
  { name: "Axiom", file: "axiom", width: 676, height: 184 },
  { name: "Meridian", file: "meridian", width: 868, height: 160 },
  { name: "Ironclad", file: "ironclad", width: 788, height: 184 },
];

function SocialProof() {
  return (
    <section className="social-proof" aria-label="Teams using Achilles">
      <p>Trusted by teams building on the frontier</p>
      <div className="logo-grid">
        {companyLogos.map((logo, index) => (
          <div className="logo-slot" key={logo.name}>
            <div
              className="logo-reel"
              style={{ animationDelay: `${index * -0.5}s` }}
            >
              {[
                logo,
                companyLogos[(index + 2) % companyLogos.length],
                logo,
              ].map((entry, i) => (
                <div className="logo-frame" key={`${entry.file}-${i}`}>
                  <Image
                    src={`/framer/${entry.file}.png`}
                    width={entry.width}
                    height={entry.height}
                    style={{ width: "auto" }}
                    alt={i === 0 ? entry.name : ""}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function FeatureIllustration({ index }: { index: number }) {
  if (index === 0)
    return (
      <div className="terminal-illustration">
        <p>$ achilles run</p>
        <p className="terminal-command">&quot;refactor auth module&quot;</p>
        <div className="terminal-output">
          <p>&gt; Planning...</p>
          <p>&gt; Writing jwt.ts</p>
        </div>
        <div className="progress-track">
          <span />
        </div>
        <div className="progress-caption">
          <span>step 4 of 6</span>
          <span>80%</span>
        </div>
        <p className="accent terminal-running">
          &gt; Running tests<span className="cursor">_</span>
        </p>
      </div>
    );
  if (index === 1)
    return (
      <div className="terminal-illustration file-tree">
        <p>src/</p>
        <p>
          ├── <span className="accent">auth/</span>
        </p>
        <p>
          │　 ├── <span className="accent">jwt.ts</span>{" "}
          <span className="reading">reading</span>
        </p>
        <p>│　 └── session.ts</p>
        <p>├── api/</p>
        <p>│　 └── router.ts</p>
        <p>└── middleware/</p>
        <div className="file-summary">14 files scanned · 3 modified</div>
      </div>
    );
  return (
    <div className="terminal-illustration pr-illustration">
      <div className="pr-name">
        <span>
          <span className="status-dot" />
          auth-refactor
        </span>
        <span className="tiny-badge">Open</span>
      </div>
      <p className="muted">PR #142 · opened 2min ago</p>
      <p>12 files changed · +87 −23</p>
      <div className="pr-checks">
        <p>
          <Icon name="check" />
          CI passing · 12/12
        </p>
        <p>
          <Icon name="check" />
          No conflicts
        </p>
        <p>
          <Icon name="check" />
          Ready to merge
        </p>
      </div>
    </div>
  );
}

function Features() {
  return (
    <section className="section" id="features-overview">
      <SectionHeading label="FEATURES">
        Ship faster. Think less. Achilles handle the rest.
      </SectionHeading>
      <div className="three-column feature-grid">
        {content.features.map((feature, index) => (
          <article
            className="numbered-card feature-card"
            key={feature.cardNumber}
          >
            <span className="number-tag">{feature.cardNumber}</span>
            <div className="offset-card">
              <div className="card-front">
                <h3>{feature.featureName}</h3>
                <FeatureIllustration index={index} />
                <div className="feature-copy">
                  <h4>{feature.title}</h4>
                  <p>{feature.description}</p>
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function UseCases() {
  const [active, setActive] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const labels = ["Fix a Bug", "Build a Feature", "Write Tests"];
  const icons: IconName[] = ["bug", "blocks", "flask"];
  const item = content.useCases[active];
  function keyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % labels.length;
    else if (event.key === "ArrowLeft")
      next = (index + labels.length - 1) % labels.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = labels.length - 1;
    else return;
    event.preventDefault();
    setActive(next);
    tabs.current[next]?.focus();
  }
  return (
    <section className="section" id="use-cases">
      <SectionHeading label="USE CASES">
        Every task a senior dev would dread. Achilles ships it.
      </SectionHeading>
      <div className="use-cases">
        <div className="tabs" role="tablist" aria-label="Use cases">
          {labels.map((label, index) => (
            <button
              key={label}
              ref={(element) => {
                tabs.current[index] = element;
              }}
              className={`tab${active === index ? " active" : ""}`}
              id={`case-tab-${index}`}
              role="tab"
              aria-selected={active === index}
              aria-controls="case-panel"
              tabIndex={active === index ? 0 : -1}
              onClick={() => setActive(index)}
              onKeyDown={(event) => keyDown(event, index)}
            >
              <Icon name={icons[index]} />
              {label}
            </button>
          ))}
        </div>
        <div
          className="use-case-panel"
          id="case-panel"
          role="tabpanel"
          aria-labelledby={`case-tab-${active}`}
          tabIndex={0}
        >
          <div className="use-case-copy">
            <div>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </div>
            <ul className="check-list">
              {[item.check1, item.check2, item.check3].map((text) => (
                <li key={text}>
                  <Icon name="check" />
                  {text}
                </li>
              ))}
            </ul>
            <Button>{item.buttonText}</Button>
          </div>
          <div className="use-case-image">
            <Image
              key={item.image}
              src={item.image}
              alt={`${labels[active]} — Achilles mission dashboard`}
              width={2156}
              height={1530}
              sizes="(max-width: 1199px) 90vw, 540px"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="section" id="how-it-works">
      <SectionHeading label="HOW IT WORKS">
        Three steps. Then get out of the way.
      </SectionHeading>
      <div className="three-column steps-grid">
        {content.steps.map((step) => (
          <article className="numbered-card step-card" key={step.cardNumber}>
            <span className="number-tag step-number">{step.cardNumber}</span>
            <div className="offset-card">
              <div className="card-front">
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function Benefits() {
  const icons: IconName[] = [
    "hourglass",
    "feather",
    "rocket",
    "eye",
    "branch",
    "shield",
  ];
  return (
    <section className="section" id="benefits">
      <SectionHeading label="BENEFITS">
        Less overhead. More output. No exceptions.
      </SectionHeading>
      <div className="benefit-grid">
        {content.benefits.map((benefit, index) => (
          <article className="benefit-card" key={benefit.title}>
            <Icon name={icons[index]} />
            <div>
              <h3>{benefit.title}</h3>
              <p>{benefit.description}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function Testimonials() {
  const track = useRef<HTMLDivElement>(null);
  function move(direction: number) {
    const width =
      track.current?.firstElementChild?.getBoundingClientRect().width ?? 400;
    track.current?.scrollBy({
      left: direction * (width + 24),
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  }
  return (
    <section className="section testimonials-section" id="testimonials">
      <SectionHeading label="TESTIMONIALS">
        Real teams. What they say after going hands-off.
      </SectionHeading>
      <div className="testimonial-carousel">
        <div
          ref={track}
          className="testimonial-track"
          tabIndex={0}
          aria-label="Customer testimonials, scroll horizontally"
        >
          {content.testimonials.map((testimonial) => (
            <figure className="testimonial-card" key={testimonial.author}>
              <div>
                <Image
                  className="testimonial-logo"
                  src={testimonial.logo}
                  width={
                    companyLogos.find((logo) =>
                      testimonial.logo.endsWith(`${logo.file}.png`),
                    )?.width ?? 120
                  }
                  height={
                    companyLogos.find((logo) =>
                      testimonial.logo.endsWith(`${logo.file}.png`),
                    )?.height ?? 24
                  }
                  style={{ width: "auto" }}
                  alt={testimonial.position.split(", ")[1]}
                />
                <blockquote>{testimonial.testimonial}</blockquote>
              </div>
              <figcaption>
                <strong>{testimonial.author}</strong>
                <span>{testimonial.position}</span>
              </figcaption>
            </figure>
          ))}
        </div>
        <div className="carousel-controls">
          <button aria-label="Previous testimonial" onClick={() => move(-1)}>
            <Icon name="arrow" className="arrow-back" />
          </button>
          <button aria-label="Next testimonial" onClick={() => move(1)}>
            <Icon name="arrow" />
          </button>
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  const [yearly, setYearly] = useState(false);
  const plans = [
    {
      name: "Starter",
      price: "$0",
      description:
        "Start running missions for free. No credit card, just connect your repo and deploy.",
      action: "Start for Free",
      features: [
        "5 missions / month",
        "1 repo connected",
        "Community support",
        "GitHub integration",
      ],
    },
    {
      name: "Pro",
      price: yearly ? "$23" : "$29",
      description:
        "For engineers who ship fast. Unlimited missions, and early access to latest models.",
      action: "Upgrade to Pro",
      features: [
        "Unlimited missions",
        "Up to 10 repos connected",
        "Priority execution queue",
        "Early access to new models",
        "Email support",
      ],
    },
    {
      name: "Enterprise",
      price: "Custom",
      description:
        "For teams that move fast at scale. Custom models and dedicated support.",
      action: "Contact Sales",
      features: [
        "Unlimited repos & seats",
        "Custom model fine-tuning",
        "Dedicated Slack channel",
        "SSO & advanced security",
        "SLA & priority support",
      ],
    },
  ];
  return (
    <section className="section pricing-section" id="pricing">
      <SectionHeading label="PRICING">
        Simple pricing. Serious output.
      </SectionHeading>
      <div className="pricing-toggle">
        <span className={!yearly ? "selected" : ""}>Monthly</span>
        <button
          role="switch"
          aria-checked={yearly}
          aria-label="Yearly billing"
          className={`billing-switch${yearly ? " on" : ""}`}
          onClick={() => setYearly(!yearly)}
        >
          <span />
        </button>
        <span className={yearly ? "selected" : ""}>Yearly</span>
        <span className="discount">
          <Icon name="check" />
          20% OFF
        </span>
      </div>
      <div className="three-column pricing-grid">
        {plans.map((plan, index) => (
          <article
            className={`pricing-card${index === 1 ? " featured-plan" : ""}`}
            key={plan.name}
          >
            <div className="plan-name">
              <h3>{plan.name}</h3>
              {index === 1 && <span className="tiny-badge">Popular</span>}
            </div>
            <div className="price" aria-live={index === 1 ? "polite" : "off"}>
              <span>{plan.price}</span>
              {index !== 2 && <small>/month</small>}
            </div>
            <p className="plan-description">{plan.description}</p>
            <Button
              secondary={index !== 1}
              href={
                index === 2
                  ? "https://www.typeform.com/"
                  : "https://framer.link/7L9chrF"
              }
            >
              {plan.action}
            </Button>
            <span className="features-caption">Features</span>
            <ul className="check-list">
              {plan.features.map((feature) => (
                <li key={feature}>
                  <Icon name="check" />
                  {feature}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function FAQ() {
  return (
    <section className="section faq-section" id="faq">
      <SectionHeading label="FAQ">
        Before you deploy. Everything you need to know.
      </SectionHeading>
      <div className="faq-list">
        {content.faqs.map((faq) => (
          <details className="faq-item" name="faq" key={faq.title}>
            <summary>
              {faq.title}
              <span className="faq-plus" aria-hidden="true" />
            </summary>
            <p>{faq.text}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="footer section">
      <div className="footer-brand">
        <Brand />
        <p>
          The autonomous coding agent
          <br />
          that ships while you sleep.
        </p>
        <div className="social-icons">
          <a
            href="https://www.twitter.com/"
            aria-label="X (Twitter)"
            target="_blank"
            rel="noreferrer"
          >
            <Icon name="x" />
          </a>
          <a
            href="https://www.linkedin.com/"
            aria-label="LinkedIn"
            target="_blank"
            rel="noreferrer"
          >
            <Icon name="linkedin" />
          </a>
          <a
            href="https://www.github.com/"
            aria-label="GitHub"
            target="_blank"
            rel="noreferrer"
          >
            <Icon name="github" />
          </a>
        </div>
        <div className="creator">
          Created by{" "}
          <Image src="/framer/arthur.jpg" alt="" width={20} height={20} />
          <a href="https://x.com/arthurdch" target="_blank" rel="noreferrer">
            Arthur
          </a>{" "}
          in{" "}
          <a href="https://framer.com/" target="_blank" rel="noreferrer">
            Framer
          </a>
        </div>
      </div>
      <div className="footer-links">
        <div>
          <h3>Navigation</h3>
          {navItems.map(([label, id]) => (
            <a href={`#${id}`} key={id}>
              {label}
            </a>
          ))}
        </div>
        <div>
          <h3>Socials</h3>
          <a href="https://www.twitter.com/" target="_blank" rel="noreferrer">
            X (Twitter)
          </a>
          <a href="https://www.linkedin.com/" target="_blank" rel="noreferrer">
            LinkedIn
          </a>
          <a href="https://www.github.com/" target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}

export function AchillesLanding() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Navigation />
      <main id="main">
        <section className="hero" id="hero">
          <BandsBackground />
          <div className="hero-inner">
            <div className="hero-copy">
              <h1>
                Your autonomous dev,
                <br className="desktop-break" /> always building.
              </h1>
              <p>
                Define the mission once. Achilles reads your codebase,
                <br className="wide-break" /> writes the code, runs the tests,
                and opens the PR.
              </p>
              <Button arrow />
            </div>
            <Image
              className="hero-dashboard"
              src="/framer/dashboard.png"
              alt="Achilles dashboard showing an auth refactor mission, execution logs, and passing tests"
              width={2156}
              height={1534}
              sizes="(max-width: 1199px) 94vw, 1080px"
              priority
            />
          </div>
        </section>
        <SocialProof />
        <Features />
        <UseCases />
        <HowItWorks />
        <Benefits />
        <Testimonials />
        <Pricing />
        <FAQ />
        <section className="final-cta">
          <div className="final-cta-copy">
            <h2>Your backlog won&apos;t clear itself.</h2>
            <p>Give Achilles a mission. Get a PR back.</p>
            <Button arrow>Deploy your first agent</Button>
          </div>
          <div className="final-dashboard">
            <Image
              src="/framer/dashboard.png"
              alt="Achilles mission workspace"
              width={2156}
              height={1534}
              sizes="(max-width: 1199px) 94vw, 1080px"
            />
          </div>
        </section>
      </main>
      <Footer />
      <div className="noise-overlay" aria-hidden="true" />
    </>
  );
}

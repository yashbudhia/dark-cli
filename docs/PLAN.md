# dark-cli — Weekend 1 Plan

## Architecture: three roles, two channels

- **Planner** — abliterated GLM (Refuseless endpoint). Adversarial hypotheses: weird inputs, boundary cases, attack payloads.
- **Operator** — vision-capable model (candidates: GLM-5V-Turbo, GLM-4.6V). Screenshot + grounding; drives the target via Playwright (web/Electron) or UIA (native Windows).
- **Verifier** — deterministic replay of the recorded action log in freshly reset state. No model in the loop. Findings exist only if they reproduce.

The CLI is the driver; the backend is the store + dashboard; the frontend visualizes runs, verified findings, and refusal telemetry.

## Milestones

1. **Model capability gate** (before product code)
   - Reads a screenshot accurately?
   - Locates and activates the correct control?
   - Completes a multi-step workflow?
   - Distinguishes an app failure from its own mistaken action?
   - Re-triggers the same failure after a state reset?
2. **Demo targets** — OWASP Juice Shop (local) + one small app with ~3 planted bugs
3. **Replay harness** — recorded UIA/Playwright action log; state-reset hooks (fresh profile dir, wiped app data, DB reset); SQLite store in backend
4. **CTF copilot mode** — sanctioned challenges; telemetry: challenges solved + refusals hit, base vs abliterated
5. **Report export** — Markdown report + executable regression test per verified finding

## Ground rules

- Authorized targets only: own apps, labs, sanctioned CTFs, bug-bounty scopes
- No features whose purpose is attacking third-party systems
- Benchmark, never assume: abliterated vs base on confirmed findings / false positives / cost

# Security review — 27 October 2026

Reviewed the pending CLI/model transport, login, runtime packaging and documentation
changes, and the existing FastAPI authentication, report ownership and payment
boundaries. Fixed the confirmed issues below before release. This is a focused code
review and automated check, not a penetration test or a guarantee of zero vulnerabilities.

## Fixed findings

### 1. Medium: cached login allowed tasks after session revocation

`cli/dark_cli/chat.py:450`, `Chat.require_account`; `cli/dark_cli/chat.py:440`, `Chat.prepare`.
The pending implementation cached account verification for five minutes and warmed
the provider connection concurrently with authentication. Removed the cache and
pre-authentication provider requests. Every new agent task now validates its session
before model execution. Tests cover missing credentials, a rejected session, revocation
between tasks, and preparation without a model connection.

### 2. Medium: incomplete model streams could produce executable tool calls

`cli/dark_cli/model.py:91`, `Stream.__aiter__`.
A clean EOF was accepted without the provider's completion terminator, potentially
executing an incomplete response. The client now requires `[DONE]`, rejects excessive
stream content, and fails before executing that response's tools. A regression test
sends a valid-looking write call without the terminator and verifies no file is written.

### 3. Medium: native-store model keys could appear in error/output text

`cli/dark_cli/model.py:58`, `status_error`; `cli/dark_cli/agent.py:224`, `Agent.clean`.
Environment-secret redaction did not cover the model key when loaded exclusively from
the OS credential store. Provider errors now redact that key before truncating the
message, agent observation/output cleaning includes it, and model configuration repr
does not include the key. Redaction is a last line of defense, not a data-loss prevention system.

### 4. Low: website lacked frame restrictions and explicit browser privacy headers

`frontend/next.config.ts:4`, `headers`.
Added frame denial, MIME sniffing protection, a cross-origin referrer policy, and
disabled camera/microphone/geolocation permissions. These supplement the API's existing
no-store responses, HTTPS cookie settings and exact-origin checks for browser mutations.

## Automated evidence

- Gitleaks 8.30.1: all reachable Git history scanned with redacted output; no findings.
- Separate exact-value check: eight locally configured credentials checked against
  478 reachable Git objects and tracked/unignored working files; no matches.
- npm production audit: no known vulnerabilities reported.
- pip-audit: no known vulnerabilities in audited installed dependencies. Local editable
  Dark packages are not published on PyPI and were reviewed as source instead.
- Python suite: 213 passing tests; Ruff passed.
- npm: seven passing tests, JavaScript syntax checks and an 11-file package allowlist passed.
- Frontend: lint, type checking and production build passed. Commands are documented in CI.

Reports containing scanner metadata are stored under ignored `output/security/`;
no credentials, OTPs, private evidence, environment files or runtime caches belong in
the published repository or npm payload.

## Important limits and deployment assumptions

- **Local agent privileges:** shell and Windows tools execute with the user's account
  privileges. Workspace file checks and prompt instructions do not sandbox these tools
  or reliably defeat prompt injection. Use trusted content or an isolated account/VM.
  Dark does not currently enforce per-action shell/desktop permission prompts.
- Login is a local-client gate. Provider requests use the user's key; website credits
  are not connected to model billing. A running task is not cancelled by account revocation.
- Agent observations and requested screenshots are sent to the configured provider.
  Report-summary uploads are separately explicit. The public docs now distinguish them.
- Auth tests exercise OTP expiry/attempt limits, CSRF, session roles, pairing retries,
  revocation and report ownership. Payment tests exercise signatures, captured-payment
  matching, ownership and idempotent credit grants. No real payment was made in this review.
- Vercel TLS, MongoDB network/user permissions, Resend/Razorpay account security and
  payment-dashboard webhook registration remain operator responsibilities.
- No full Office/Chrome compatibility or broad adversarial desktop assessment was performed.
- MIT licensing covers original code; third-party and historical visual asset exceptions
  are listed in `THIRD_PARTY_NOTICES.md`.

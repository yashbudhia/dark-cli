# Email accounts and CLI pairing

Dark uses MongoDB for users, one-time email challenges, sessions, pairing requests,
rate limits and user-owned run records. Cloudflare delivers sign-in codes through
its Email Sending REST API. The first successful email verification creates an
account; later verifications sign in to the same account.

Email sign-in is passwordless authentication. CLI connection is a first-party,
device-style pairing flow. It is not an OAuth provider implementation: the endpoints
accept JSON, have no OAuth client registration or scopes, and do not issue refresh
tokens. No external identity provider is required.

## Credentials to supply later

Copy `.env.example` to the repository-root `.env` and set:

| Variable | Value |
| --- | --- |
| `MONGODB_URI` | MongoDB connection string, including credentials if needed |
| `MONGODB_DATABASE` | Database name; defaults to `dark` |
| `DARK_AUTH_SECRET` | Random secret of at least 32 characters; keep stable across restarts |
| `DARK_WEB_URL` | Exact website origin, with no trailing slash, e.g. `https://dark.example` |
| `CLOUDFLARE_ACCOUNT_ID` | Account with Email Sending enabled |
| `CLOUDFLARE_API_TOKEN` | Account-scoped token with Email Sending edit permission |
| `DARK_EMAIL_FROM` | Sender email on the domain onboarded for Email Sending |

Generate the auth secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

These variables belong on the backend. Never add them to `NEXT_PUBLIC_*` variables.
Missing database or auth-secret configuration returns HTTP 503 for account APIs;
there is no console-code, fixed-code, or in-memory production fallback. Missing
email configuration prevents code requests. `/health` reports whether auth storage
was configured, not whether email has been delivered or Mongo remains reachable.

Cloudflare's [Email Service](https://developers.cloudflare.com/email-service/)
supports outbound transactional email through the
[REST API](https://developers.cloudflare.com/api/resources/email_sending/methods/send/).
Sending to arbitrary recipients requires Workers Paid and Email Sending Beta
access. Email Routing alone can send only to destination addresses already
verified in the Cloudflare account. Onboard the sender domain and apply the
required DNS authentication records before testing public signup.

## Run locally

From the repository root:

```powershell
uv pip install --python .venv\Scripts\python.exe -e './backend[dev]' -e './cli[dev]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

The default origins are `http://127.0.0.1:3000` for the website and
`http://127.0.0.1:8000` for the backend. Use the same website hostname everywhere;
`localhost` and `127.0.0.1` have different origins and cookie scopes. Next.js
proxies `/api/*` to `DARK_BACKEND_URL`, configured in the Next.js environment.
When running Next from `frontend/`, set that override in `frontend/.env.local`
if needed; the default backend URL needs no override. CLI `.env` loading reads
`DARK_SERVER_URL` from the repository root when invoked there. Elsewhere, set
the environment variable explicitly or pass `--server`.

Open `/login`, enter your email, and verify its eight-digit code. Then:

```powershell
.\.venv\Scripts\dark.exe login
.\.venv\Scripts\dark.exe whoami
.\.venv\Scripts\dark.exe logout

# Another website or a terminal without a browser:
.\.venv\Scripts\dark.exe login --server https://dark.example --no-browser
```

`dark login` opens `/connect?code=...`. Sign-in preserves that destination. The
website displays the requesting computer and requires confirmation that the code
matches the terminal. Approve or decline explicitly. `/dashboard` shows connected
CLI sessions, lets you revoke them, and lists run records submitted to the API.
Desktop commands continue saving evidence locally. Use the explicit upload
command below to send a report; remote task dispatch is not implemented.

## Upload a desktop report

After a probe or exercise has produced a `report.json`, run:

```powershell
# Review the exact content without credentials or a network request.
.\.venv\Scripts\dark.exe runs upload .dark\runs\<run-directory> --dry-run

# Upload using the account connected by dark login.
.\.venv\Scripts\dark.exe runs upload .dark\runs\<run-directory> --open
```

The export contains the window title, scenario name, outcome, completion time,
assertions with expected and observed text, and any reason or error message.
It excludes the local evidence-directory field, window handles, raw snapshots,
screenshots, event logs and tool metadata. Text inside assertions and error
messages is preserved, so review the dry-run output before uploading a report
from an application containing private data. Local reports over 256 KiB and
malformed reports are rejected before any upload.

Each export has a stable SHA-256 fingerprint. Uploads use an idempotent PUT,
so retrying the same export updates the same owner-scoped record. An interrupted
request can be retried with the same command. Changing exported content creates
a new record. Uploaded reports always have `verified_finding: false`.

The workspace lists the latest 100 saved runs. Open a row to view its report at
`/dashboard/runs/<id>` with the expected and observed values of each assertion.
Direct report links preserve their destination through sign-in. The source
reports currently record completion time; imported runs use that timestamp for
ordering and do not infer a run duration.

## Session behavior

- Sign-in codes: eight random digits, ten-minute lifetime, at most five attempts,
  single-use atomic consumption. Challenge IDs and code digests are bound together.
- Email sending: one request per email per fixed 60-second window and twenty
  requests per IP per ten-minute window. Verification and pairing also have limits.
- Browser sessions: seven days; HttpOnly, SameSite=Lax, host-only cookie scoped to
  `/api`. Secure is enabled for HTTPS. All browser mutations require the configured
  website Origin. Browser tokens are never returned in JSON.
- CLI sessions: thirty days; opaque bearer token, stored through Python keyring
  (Windows Credential Manager on Windows). Tokens are scoped locally by server
  origin. No plaintext credential file is created; unavailable keyrings fail closed.
- Pairing: ten minutes, five-second polling, increased wait on `slow_down`, one-time
  token exchange, explicit approval or denial. Bearer CLI tokens cannot approve
  computers or manage other device credentials.
- Mongo stores HMAC digests of codes and session tokens, not their plaintext.
  TTL indexes clean expired records, while queries enforce expiry immediately.
  Changing the auth secret invalidates existing credentials.
- Revoking a computer or logging out deletes its server session. CLI logout keeps
  the local credential on network failure so revocation can be retried. The explicit
  `--local-only` option forgets it without claiming remote revocation.
- Runs, findings and refusal events require a session and are scoped to its owner.
  The prior unowned in-memory scaffold data is not migrated.

Serve production traffic over HTTPS and expose the API through the same website
origin. Configure the ASGI server's trusted proxy addresses for your actual
reverse proxy so rate limits see the intended client IP. Do not trust arbitrary
forwarded headers or expose a proxy-trusted backend port publicly. The code uses
the ASGI peer address, which Uvicorn can populate from trusted proxy headers.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests cli\tests -q
.\.venv\Scripts\python.exe -m ruff check backend\app\auth.py backend\app\auth_routes.py backend\app\email.py backend\app\settings.py backend\app\main.py backend\tests cli
cd frontend
npm run lint
npm run build
```

Automated auth tests use mongomock and a captured mail adapter, and cover the
Cloudflare HTTP contract with mocked responses. Actual MongoDB connectivity and
email delivery must be verified after credentials are supplied. No test email is
sent by the automated suite.

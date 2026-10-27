# Email accounts and CLI pairing

Dark uses MongoDB for users, one-time email challenges, sessions, pairing requests,
rate limits and user-owned run records. Resend delivers sign-in codes through
its email REST API; Cloudflare remains an optional provider. The first successful email verification creates an
account; later verifications sign in to the same account.

Email sign-in is passwordless authentication. CLI connection is a first-party,
device-style pairing flow. It is not an OAuth provider implementation: the endpoints
accept JSON, have no OAuth client registration or scopes, and do not issue refresh
tokens. No external identity provider is required.

## Credentials to supply later

Run `scripts/setup-service.ps1 -Dev` to initialize the ignored root `.env` and
generate its auth secret without overwriting existing credentials. Set:

| Variable | Value |
| --- | --- |
| `MONGODB_URI` | MongoDB connection string, including credentials if needed |
| `MONGODB_DATABASE` | Database name; defaults to `dark` |
| `DARK_AUTH_SECRET` | Random secret of at least 32 characters; keep stable across restarts |
| `DARK_WEB_URL` | Exact website origin, with no trailing slash, e.g. `https://dark.example` |
| `DARK_EMAIL_PROVIDER` | `resend` or `cloudflare`; inferred from a Resend key when unset |
| `RESEND_API_KEY` | Resend API key authorized to send from the configured domain |
| `DARK_EMAIL_FROM` | Sender email on a verified sending domain |

For `DARK_EMAIL_PROVIDER=cloudflare`, configure `CLOUDFLARE_ACCOUNT_ID` and
`CLOUDFLARE_API_TOKEN` instead of `RESEND_API_KEY`.

If configuring a hosted environment without the setup script, generate a secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

These variables belong on the backend. Never add them to `NEXT_PUBLIC_*` variables.
Missing database or auth-secret configuration returns HTTP 503 for account APIs;
there is no console-code, fixed-code, or in-memory production fallback. Missing
email configuration prevents code requests. `/health` reports whether auth storage
was configured, not whether email has been delivered or Mongo remains reachable.
`GET /api/auth/readiness` and `dark doctor` check configuration presence and ping
MongoDB without sending email. A ready result has HTTP 200; missing configuration
or unreachable storage returns HTTP 503. Email delivery is explicitly unverified
until a real code arrives. `dark doctor` exits 2 for a not-ready service and 1 for
connection/protocol errors.

Resend uses the [Send Email API](https://resend.com/docs/api-reference/emails/send-email).
Verify a sending domain, authorize the key for that domain, and configure
`DARK_EMAIL_FROM` explicitly. There is no hardcoded production sender. For a safe
provider test, use Resend's [test recipients](https://resend.com/docs/dashboard/emails/send-test-emails),
such as `delivered+dark-demo@resend.dev`. These simulate delivery events and count
against the account's sending quota.

For the optional Cloudflare provider, [Email Service](https://developers.cloudflare.com/email-service/)
supports outbound transactional email through the
[REST API](https://developers.cloudflare.com/api/resources/email_sending/methods/send/).
Sending to arbitrary recipients requires Workers Paid and Email Sending Beta
access. Email Routing alone can send only to destination addresses already
verified in the Cloudflare account. Onboard the sender domain and apply the
required DNS authentication records before testing public signup.

## Run locally

The combined runner starts both processes and loads the root environment:

```powershell
.\scripts\start-service.ps1
```

For separate terminals, from the repository root:

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
if needed; the default backend URL needs no override.

The installed CLI discovers `.env` from its working directory and parent
directories. `DARK_ENV_FILE` selects an explicit file. Server selection is
`--server`, then `DARK_SERVER_URL`, then the server remembered after login, then
`https://dark-cli-web.vercel.app`. An explicitly configured environment URL overrides the
remembered preference; change or clear it when switching websites. The non-secret
server preference lives in the per-user Dark config directory; `DARK_CONFIG_DIR`
can override that location. Tokens remain in the native OS credential store.
Clients on other computers need only the website URL and their own login, not
the MongoDB or email-provider service credentials.

Open `/login`, enter your email, and verify its eight-digit code. Then:

```powershell
.\.venv\Scripts\dark.exe login --server http://127.0.0.1:3000
.\.venv\Scripts\dark.exe doctor
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
.\.venv\Scripts\dark.exe runs list
.\.venv\Scripts\dark.exe runs show <run-id> --open
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
.\scripts\verify-service.ps1
```

Automated auth tests use mongomock and a captured mail adapter, and cover the
email-provider HTTP contracts with mocked responses. Actual MongoDB connectivity and
email delivery must be verified after credentials are supplied. No test email is
sent by the automated suite.

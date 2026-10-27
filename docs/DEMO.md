# Account and CLI demo

The implemented demo connects a terminal to an email account, uploads a saved
desktop test report and displays its assertions in the workspace. It uses MongoDB
for persistence and Resend for sign-in codes. Autonomous
computer-use planning remains a separate increment.

## Prepare once

From the repository root, with Python/uv and Node/npm available:

```powershell
.\scripts\setup-service.ps1 -Dev
```

Setup installs Python packages and frontend dependencies, creates `.env` if
needed, fills missing configuration keys and generates `DARK_AUTH_SECRET` only
when its file value is empty. Existing credentials and secrets are preserved.
The secret is not printed.

Fill these values in the root `.env`:

```dotenv
MONGODB_URI=
RESEND_API_KEY=
DARK_EMAIL_FROM=
```

Keep `DARK_AUTH_SECRET` stable. For a local demo, keep the website origin
`DARK_WEB_URL=http://127.0.0.1:3000`. Resend needs a verified sending domain and
an API key authorized for that domain. Provider configuration details, including
the optional Cloudflare adapter, are in [AUTH.md](AUTH.md).

## Start the service

```powershell
.\scripts\start-service.ps1

# For a production build rather than the Next.js development server:
.\scripts\start-service.ps1 -Production
```

The website is at `http://127.0.0.1:3000`. The API binds to loopback on port 8000;
the website proxies `/api` to it. One Ctrl+C stops both launched processes.
Occupied ports are reported instead of stopping existing processes. Stop any
older development servers before starting this combined runner.

Use `-FrontendPort 3010 -BackendPort 8010` for another local pair of ports. The
runner adjusts a loopback website origin and the web proxy together. A production
start builds the frontend with that proxy configuration before serving it.
Use that same origin with `--server` on CLI commands, or set `DARK_SERVER_URL`
in the second terminal. The startup output shows the correct website origin.
`-AllowUnconfigured` is available for visual previews; account APIs stay unavailable
until configured and no test accounts or sign-in codes are generated.

## Run the demo

Use a second terminal at the repository root. The full executable paths avoid
depending on PowerShell environment activation:

```powershell
.\.venv\Scripts\dark.exe doctor
.\.venv\Scripts\dark.exe login
.\.venv\Scripts\dark.exe whoami
```

`doctor` checks configuration and MongoDB reachability without sending email.
It exits 2 if configuration/storage is not ready and 1 for connection/protocol
errors. A successful check exits 0.
Actual email delivery is confirmed by the following login. The CLI opens the
website, where you enter an email, verify its code and approve the computer after
matching the pairing code. `whoami` should show the same email.

Use a completed run directory under `.dark/runs`:

```powershell
.\.venv\Scripts\dark.exe runs upload .dark\runs\<run-directory> --dry-run
.\.venv\Scripts\dark.exe runs upload .dark\runs\<run-directory> --open
.\.venv\Scripts\dark.exe runs list
```

The dry run shows the export before anything is sent. The upload opens a report
with its outcome, expected versus observed text, and JSON export. Upload the same
directory again: it should return the same report ID and leave one workspace row.

If no run exists yet, the disposable Windows fixture can produce one. This
requires the separate desktop adapter setup described in the repository README:

```powershell
.\scripts\setup-desktop.ps1
.\scripts\start-desktop-fixture.ps1
.\.venv\Scripts\dark.exe desktop probe --title 'Dark Desktop Fixture' --expect Ready
```

To demonstrate an actual failed assertion, run the fixture's negative scenario;
exit code 1 is expected because the fixture deliberately accepts the quantity:

```powershell
.\.venv\Scripts\dark.exe desktop exercise examples\desktop\negative.json --apply
```

Use the `evidence_dir` printed by the command as the upload directory. A failed
assertion is displayed as a test result, without automatic promotion to a verified
security finding. Raw snapshots, screenshots and event logs stay local.

Finally, revoke the computer in the workspace and confirm `dark whoami` requires
login again, or run `dark logout` to revoke the current session from the terminal.

## Verification

```powershell
.\scripts\verify-service.ps1
```

Automated tests use synthetic MongoDB/email adapters, test HTTP contracts, and do
not send real email. After real credentials are configured, perform the login,
upload/retry, revocation and restart checks above against the running service.
Restarting should preserve accounts, valid sessions and uploaded reports in MongoDB.

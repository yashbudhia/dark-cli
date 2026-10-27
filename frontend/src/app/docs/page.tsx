import Image from "next/image";
import Link from "next/link";
import "./docs.css";

export const metadata = {
  title: "Docs — Dark",
  description: "Install the Dark CLI, connect your account, inspect Windows apps and run explicit test scenarios.",
};

const sections = [
  ["install", "Install"],
  ["login", "Connect your account"],
  ["desktop", "Inspect a Windows app"],
  ["scenarios", "Run a scenario"],
  ["reports", "Upload and view reports"],
  ["credits", "Credits"],
  ["configuration", "Configuration"],
  ["troubleshooting", "Troubleshooting"],
] as const;

function Code({ children, label }: { children: string; label?: string }) {
  return <figure className="docs-code">
    {label && <figcaption>{label}</figcaption>}
    <pre><code>{children}</code></pre>
  </figure>;
}

export default function DocsPage() {
  return <div className="docs-shell">
    <header className="docs-header">
      <Link href="/" className="docs-brand" aria-label="Dark home">
        <Image src="/dark-mark.svg" width={30} height={30} alt="" />dark<span>/</span>
      </Link>
      <nav className="docs-header-nav"><Link href="/">Home</Link><Link href="/login">Sign in</Link></nav>
    </header>
    <div className="docs-body">
      <nav className="docs-toc" aria-label="On this page">
        <span>Documentation</span>
        {sections.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
      </nav>
      <main className="docs-content">
        <span className="docs-eyebrow">DOCS</span>
        <h1>Get started with Dark</h1>
        <p className="docs-lead">Dark inspects native Windows apps, runs explicit test scenarios, and saves the evidence
          you need to investigate a failure. Desktop tools run on your computer. In agent chat, prompts, tool results and
          requested screenshots are sent to your configured model provider.</p>

        <section id="install"><h2>Install</h2>
          <p>You need Node.js 20.11 or newer. Then install the CLI globally:</p>
          <Code label="terminal">{`npm i -g dark-agent-cli
dark --version`}</Code>
          <p>The first command you run sets up a private runtime for you, so no Python, uv or Git checkout is needed.
            This needs an internet connection once. Later commands reuse it.</p>
          <p>To try it without installing globally:</p>
          <Code>{`npx --package dark-agent-cli dark login`}</Code>
          <p className="docs-note">Desktop control works on Windows 10/11 (x64). Account and report commands also work on macOS and Linux.</p>
        </section>

        <section id="login"><h2>Connect your account</h2>
          <p>Sign-in uses an email code on the website, then a pairing code that links your terminal.</p>
          <Code label="terminal">{`dark login      # opens your browser; confirm the pairing code
dark whoami     # shows the connected account and server
dark doctor     # checks the setup
dark logout     # removes the local session`}</Code>
          <p>Your session is stored in the operating system credential store, never in a plain text file.
            Revoke any connected computer from the <Link href="/dashboard">workspace</Link>.</p>
        </section>

        <section id="desktop"><h2>Inspect a Windows app</h2>
          <p>Desktop commands use the Windows MCP server, which Dark downloads and verifies by checksum on first use.
            Start by checking the handshake and listing windows:</p>
          <Code label="powershell">{`dark desktop doctor
dark desktop windows`}</Code>
          <p>Pick the exact window title from that list, then probe it. A probe only reads: it never clicks or types.</p>
          <Code label="powershell">{`dark desktop probe --title "My App" --screenshot
dark desktop probe --title "My App" --expect "Ready"`}</Code>
          <ul>
            <li><code>--expect</code> checks that text appears in the app&apos;s controls. Repeat it for several checks.</li>
            <li><code>--screenshot</code> saves a PNG of only that window.</li>
            <li>Results go to <code>.dark/runs/&lt;run&gt;/</code> as a snapshot, an append-only event log and <code>report.json</code>.</li>
          </ul>
          <p>A passed check is an observation, not a verified vulnerability. Reports mark the difference between
            observed, passed, failed and error.</p>
        </section>

        <section id="scenarios"><h2>Run a scenario</h2>
          <p>A scenario is a short JSON file of explicit steps. It must end with an <code>assert_text</code> step so
            every run proves an outcome.</p>
          <Code label="negative.json">{`{
  "name": "Reject a negative inventory quantity",
  "window_title": "Dark Desktop Fixture",
  "steps": [
    {"action": "click", "automation_id": "resetButton"},
    {"action": "assert_text", "automation_id": "statusLabel", "text": "Ready"},
    {"action": "type", "automation_id": "quantityInput", "text": "-2"},
    {"action": "click", "automation_id": "saveButton"},
    {"action": "assert_text", "automation_id": "statusLabel",
     "text": "Rejected: quantity must be nonnegative"}
  ]
}`}</Code>
          <p>Without <code>--apply</code> the command only validates and previews. Add it to really click and type:</p>
          <Code label="powershell">{`dark desktop exercise negative.json           # preview only
dark desktop exercise negative.json --apply   # runs the steps; exit code 1 if an assertion fails`}</Code>
          <div className="docs-table-wrap"><table>
            <thead><tr><th>Field</th><th>Meaning</th></tr></thead>
            <tbody>
              <tr><td><code>action</code></td><td><code>click</code>, <code>type</code> or <code>assert_text</code></td></tr>
              <tr><td><code>automation_id</code> / <code>name</code></td><td>How to find the control. One of them is required, and it must match exactly one control.</td></tr>
              <tr><td><code>control_type</code></td><td>Optional filter, for example <code>Button</code>.</td></tr>
              <tr><td><code>text</code></td><td>Text to type, or the text to expect.</td></tr>
              <tr><td><code>match</code></td><td><code>exact</code> (default, ignores case) or <code>contains</code>.</td></tr>
            </tbody>
          </table></div>
          <p>A scenario has up to 25 steps. A failed assertion stops the run. Mutating steps are never retried after a
            timeout, because their outcome may be unknown.</p>
          <p className="docs-note">Scenarios do not reset the app&apos;s data. Define and check a reset step before treating a repeated
            failure as reproducible.</p>
        </section>

        <section id="reports"><h2>Upload and view reports</h2>
          <p>Uploading is always explicit. Preview exactly what would be sent first:</p>
          <Code label="powershell">{`dark runs upload .dark\\runs\\<run-directory> --dry-run
dark runs upload .dark\\runs\\<run-directory> --open
dark runs list
dark runs show <run-id>`}</Code>
          <p>An upload contains the report summary and its expected-versus-observed text. Raw snapshots, screenshots and
            event logs stay on your computer. Uploading the same report again is safe and updates the same entry.</p>
        </section>

        <section id="credits"><h2>Credits</h2>
          <p>New accounts get a free $1 credit to try Dark. Add more on the <Link href="/billing">billing page</Link>:
            recharge $10 and get $5 extra, so $15 in credits. Credits are a one-time prepaid balance with no subscription.
            Payments are handled by Razorpay.</p>
          <p>Agent chat currently uses your own model provider key and is billed by that provider.
            Website credits do not pay for model requests yet.</p>
        </section>

        <section id="configuration"><h2>Configuration</h2>
          <p>Dark reads a <code>.env</code> file from the working directory or a parent folder. These variables are optional:</p>
          <div className="docs-table-wrap"><table>
            <thead><tr><th>Variable</th><th>Purpose</th></tr></thead>
            <tbody>
              <tr><td><code>DARK_SERVER_URL</code></td><td>Use another Dark service instead of the hosted site. <code>dark login --server</code> does the same.</td></tr>
              <tr><td><code>DARK_ENV_FILE</code></td><td>Read this specific environment file.</td></tr>
              <tr><td><code>DARK_CONFIG_DIR</code></td><td>Where non-secret preferences are saved.</td></tr>
              <tr><td><code>DARK_WINDOWS_MCP_PATH</code></td><td>Your own Windows MCP server executable, needed on non-x64 Windows.</td></tr>
              <tr><td><code>DARK_RUNTIME_DIR</code></td><td>Where the private runtime is installed.</td></tr>
              <tr><td><code>DARK_NO_SPINNER</code></td><td>Set to any value to turn off the progress spinner.</td></tr>
            </tbody>
          </table></div>
          <p>Keep MongoDB, email-provider and payment-service secrets on your server. The CLI stores its own session and
            your model provider key in the operating system credential store.</p>
        </section>

        <section id="troubleshooting"><h2>Troubleshooting</h2>
          <dl className="docs-faq">
            <dt>&ldquo;Window title is ambiguous&rdquo; or not found</dt>
            <dd>Run <code>dark desktop windows</code> and copy the exact, unique title.</dd>
            <dt><code>dark</code> is not recognized after install</dt>
            <dd>Open a new terminal so your PATH refreshes, or check that the folder printed by <code>npm prefix -g</code> is on it.</dd>
            <dt>Login says the pairing expired</dt>
            <dd>Pairing codes last 10 minutes. Run <code>dark login</code> again.</dd>
            <dt>A step timed out</dt>
            <dd>The outcome is unknown. Look at the app, then run the scenario again from a reset state.</dd>
            <dt>Spinner characters look wrong in a log</dt>
            <dd>Output is clean when piped. If you still see it, set <code>DARK_NO_SPINNER=1</code>.</dd>
          </dl>
        </section>
      </main>
    </div>
  </div>;
}

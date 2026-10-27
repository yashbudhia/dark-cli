# Security

Report vulnerabilities privately through [GitHub security advisories](https://github.com/yashbudhia/dark-cli/security/advisories/new).
Do not put credentials, email codes, pairing secrets or private desktop evidence in public issues.
Include the version, reproduction steps with synthetic data, and the expected and observed behavior.

## Trust and privacy

Dark is a local agent with terminal and desktop access, **not a sandbox**. Model-requested
commands run with your user permissions. File-tool workspace checks do not constrain
the shell or Windows MCP server. Use a disposable workspace or a separate Windows account
for untrusted repositories, documents and websites. Do not run Dark elevated.
Prompt instructions to ask before sensitive actions are not a security boundary.

Agent prompts, file/tool observations and requested screenshots go to the provider
you configure. Avoid confidential windows and content. Report uploads are separate
and explicit: they contain report summaries and assertions, not raw screenshots.

Model keys and CLI session tokens use the native operating-system credential store.
Conversation transcripts and input history are saved as local plaintext in the
CLI config directory. Configured credentials are redacted before saving; arbitrary
sensitive content may remain. Set `DARK_NO_HISTORY=1` to disable new history files.
Resume selects conversations for the current workspace.
Hosted MongoDB, email and payment credentials belong only on the server. Keep `.env`,
`.vercel`, runtime caches and `.dark` evidence out of Git. Read and verify a pairing
code in your own terminal before approving it in the browser.

The CLI validates its Dark session before each agent task. Revocation blocks the
next task; it does not interrupt an already running task. Local login checks are
client behavior, not a model-provider billing or access-control boundary.
Model requests currently use your own provider key, independently of website credits.

## Releases

Use the latest published CLI version. Downloaded runtime and Windows MCP archives
are pinned and checksum-verified; packaged Python requirements are hash locked.
These checks establish artifact integrity, not that upstream software has no bugs.
See [the security review](security_best_practices_report.md) for the checked scope and limits.

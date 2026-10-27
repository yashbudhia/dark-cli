# Dark CLI

Install with Node.js 20.11 or newer:

```sh
npm install -g dark-agent-cli
dark
```

Or run without a global installation:

```sh
npx --package dark-agent-cli dark login
```

Plain `dark` opens a conversational terminal with streamed replies and visible tool
calls. Type a task such as "create a Python script and run it" or "open Windows
Settings". The agent can read/write workspace files, run terminal commands, and
load native Windows tools for inspecting and controlling applications.

```text
❯ /help
❯ /login
❯ Create hello.py that prints hello, then run it and check the output.
❯ /update
```

Use `/provider` to configure an OpenAI-compatible endpoint and model key. Keys are
stored in the native OS credential store. `DARK_API_KEY`, `DARK_BASE_URL` and
`DARK_MODEL` in a local `.env` are also supported; Refuseless is the default
provider. Account login manages report storage and devices; model calls currently
use your own provider key, independently of the website credit balance.

Slash commands include `/help`, `/login`, `/logout`, `/whoami`, `/doctor`, `/provider`,
`/model`, `/tools`, `/desktop`, `/runs`, `/cwd`, `/clear`, `/update` and `/exit`.
Tab completes commands, Alt+Enter inserts a newline, and Ctrl+C stops an active
task. Conversation history stays in memory for the current session.

For one task without an interactive session:

```sh
dark run "Read this project's README and summarize the setup steps"
```

`/login` opens https://dark-cli-web.vercel.app for email sign-in and computer approval.
The CLI session is saved in your native OS credential store. Linux needs a working
Secret Service/KWallet keyring; Windows and macOS use their native stores.

On first use, the launcher downloads a pinned, SHA-256-verified uv runtime, installs
Python 3.12 privately, and installs the bundled Dark CLI wheel with hash-locked
dependencies. No existing Python, uv, Git checkout, or PyPI publication is needed.
Internet access is required for first-run setup. Later commands reuse that runtime.
The npm install itself needs no lifecycle scripts and also works with `--ignore-scripts`.

Account/report commands support Windows, macOS, and glibc Linux on x64/arm64.
Windows desktop commands automatically install the pinned, SHA-256-verified
[Windows MCP server](https://github.com/sbroenne/mcp-windows) on Windows x64.
Other Windows architectures need `DARK_WINDOWS_MCP_PATH`; macOS/Linux desktop
control is not implemented.

```sh
dark desktop doctor
dark desktop windows
dark runs upload /path/to/run --dry-run
dark runs upload /path/to/run
dark runs list
dark logout
```

The interactive agent executes model-selected tools. The separate `scan` and `ctf`
pipelines for replay-verified security findings are still in development.

## Updating

```sh
dark update
```

Or use `/update` in chat to install the latest global npm version and restart Dark.
Local/npx installations show the appropriate install command instead of modifying
a different global installation. Updating from 0.1.0 requires running
`npm install -g dark-agent-cli@latest` once to get these new commands.

## Configuration

`dark login` defaults to the hosted website. `--server` and `DARK_SERVER_URL` can
select another service. The CLI also reads `.env` from the working directory or
its parents; `DARK_ENV_FILE` selects a specific file. Hosted-service credentials
(MongoDB, Resend and service signing keys) are never needed on client machines.
Model keys are separate from your account login and can be set in your local `.env`.

The runtime lives under `%LOCALAPPDATA%\Dark\runtime` on Windows or
`${XDG_CACHE_HOME:-~/.cache}/dark-cli` elsewhere. `DARK_RUNTIME_DIR` overrides it.
To reset runtime installation, remove only that runtime directory and rerun `dark`.
Sign out with `dark logout` before uninstalling if you also want to revoke the session.

## Maintainers

From this repository's `npm/` directory, with uv installed:

```sh
npm test
npm run check
npm pack
npm login
npm publish --access public
```

`prepack` builds the CLI wheel from `../cli`; only the launcher, wheel, dependency
lock, extraction helper and README are shipped. No GitHub access is needed to install.
Both Python and npm versions must match. To update dependency pins from the repo root:

```sh
uv pip compile cli/pyproject.toml --python-version 3.12 --universal --generate-hashes --output-file npm/python/requirements.txt
```

Test the resulting tarball from an unrelated directory before publishing. Package
publication requires an npm account with publishing authentication enabled.

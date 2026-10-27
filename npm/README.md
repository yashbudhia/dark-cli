# Dark CLI

Install with Node.js 20.11 or newer:

```sh
npm install -g dark-agent-cli
dark login
dark doctor
```

Or run without a global installation:

```sh
npx --package dark-agent-cli dark login
```

Dark opens https://dark-cli-web.vercel.app for email sign-in and computer approval.
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

Native desktop probes and explicit scenarios are available. Autonomous model-guided
scanning is still in development. Installing this package does not enable that feature.

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

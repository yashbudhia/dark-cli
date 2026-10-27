"use client";

import { useState } from "react";

const COMMAND = "npm i -g dark-agent-cli";

export function InstallCommand() {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(COMMAND);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch { /* Clipboard is unavailable on insecure origins; the command stays selectable. */ }
  }

  return <div className="install">
    <div className="install-line">
      <code><span aria-hidden="true">$ </span>{COMMAND}</code>
      <button type="button" className="install-copy" onClick={() => void copy()} aria-label="Copy install command">
        {copied ? "Copied ✓" : "Copy"}
      </button>
    </div>
    <p className="install-note">Installs the <code>dark</code> command. Needs Node.js 20.11 or newer.</p>
    <span className="sr-only" role="status">{copied ? "Install command copied" : ""}</span>
  </div>;
}

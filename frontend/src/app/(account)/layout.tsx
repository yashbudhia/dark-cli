import Link from "next/link";
import "./account.css";

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return <div className="account-shell">
    <header className="account-header">
      <Link href="/" className="account-brand" aria-label="Dark home">
        <svg width="30" height="30" viewBox="0 0 64 64" aria-hidden="true">
          <defs><mask id="account-moon"><rect width="64" height="64" fill="#fff" /><circle cx="39" cy="25" r="17" fill="#000" /></mask></defs>
          <rect width="64" height="64" rx="14" fill="#080d0a" />
          <circle cx="29" cy="35" r="20" fill="#eef4ef" mask="url(#account-moon)" />
          <path d="M38 38 48 16" stroke="#00ff88" strokeWidth="5.5" strokeLinecap="square" fill="none" />
        </svg>dark<span>/</span>
      </Link>
      <nav className="account-header-nav">
        <Link href="/billing" className="account-header-link">Billing</Link>
        <Link href="/dashboard" className="account-header-link">Your workspace</Link>
      </nav>
    </header>
    <main className="account-main">{children}</main>
    <footer className="account-footer">Your computer. Your session. Your evidence.</footer>
  </div>;
}

import Link from "next/link";
import "./account.css";

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return <div className="account-shell">
    <header className="account-header">
      <Link href="/" className="account-brand" aria-label="Dark home">
        <svg width="30" height="30" viewBox="0 0 64 64" aria-hidden="true">
          <rect width="64" height="64" rx="11" fill="#080d0a" />
          <path d="M26 11H11v15M38 11h15v15M53 38v15H38M26 53H11V38" fill="none" stroke="#eef4ef" strokeWidth="6" strokeLinecap="square" />
          <path d="M18 32h28M32 25v14" fill="none" stroke="#00ff88" strokeWidth="5" strokeLinecap="square" />
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

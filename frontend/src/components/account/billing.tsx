"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AccountError, accountApi, errorMessage, redirectToSignIn } from "@/lib/account-api";
import type { Account, Balance, Order, Pack } from "@/lib/account-api";

const CHECKOUT_SCRIPT = "https://checkout.razorpay.com/v1/checkout.js";

type CheckoutResult = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };
type CheckoutOptions = {
  key: string; order_id: string; amount: number; currency: string; name: string; description: string;
  prefill: { email: string }; theme: { color: string };
  handler: (result: CheckoutResult) => void;
  modal: { ondismiss: () => void };
};
declare global {
  interface Window {
    Razorpay?: new (options: CheckoutOptions) => { open: () => void; on: (event: string, cb: (e: { error: { description: string } }) => void) => void };
  }
}

let checkoutPromise: Promise<boolean> | undefined;

function loadCheckout(): Promise<boolean> {
  if (window.Razorpay) return Promise.resolve(true);
  if (checkoutPromise) return checkoutPromise;
  checkoutPromise = new Promise(resolve => {
    const script = document.createElement("script");
    const finish = (ready: boolean) => {
      clearTimeout(timeout);
      script.onload = script.onerror = null;
      if (!ready) { script.remove(); checkoutPromise = undefined; }
      resolve(ready);
    };
    const timeout = setTimeout(() => finish(false), 15000);
    script.src = CHECKOUT_SCRIPT;
    script.async = true;
    script.onload = () => finish(Boolean(window.Razorpay));
    script.onerror = () => finish(false);
    document.body.appendChild(script);
  });
  return checkoutPromise;
}

const money = (cents: number) => `$${(cents / 100).toFixed(cents % 100 ? 2 : 0)}`;

export function Billing() {
  const [account, setAccount] = useState<Account | null>(null);
  const [packs, setPacks] = useState<Pack[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [wallet, setWallet] = useState<Balance>({ balance_cents: 0, currency: "USD", trial_cents: 100 });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [user, catalog, current] = await Promise.all([
          accountApi<Account>("/auth/me"),
          accountApi<{ enabled: boolean; packs: Pack[] }>("/billing/plans"),
          accountApi<Balance>("/billing/status"),
        ]);
        if (active) { setAccount(user); setPacks(catalog.packs); setEnabled(catalog.enabled); setWallet(current); }
      } catch (failure) {
        if (!active) return;
        if (failure instanceof AccountError && failure.status === 401) redirectToSignIn();
        else setError(errorMessage(failure));
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, []);

  async function buy(pack: Pack) {
    setBusy(pack.id); setError(""); setNotice("");
    try {
      const [order, ready] = await Promise.all([
        accountApi<Order>("/billing/order", { method: "POST", body: JSON.stringify({ pack: pack.id }) }),
        loadCheckout(),
      ]);
      if (!ready || !window.Razorpay) throw new Error("Could not load Razorpay checkout. Check your connection and try again.");
      const checkout = new window.Razorpay({
        key: order.key_id, order_id: order.order_id, amount: order.amount, currency: order.currency,
        name: "Dark", description: order.name, prefill: { email: order.email }, theme: { color: "#00ff88" },
        handler: result => void confirm(result),
        modal: { ondismiss: () => setBusy("") },
      });
      checkout.on("payment.failed", event => { setError(event.error.description || "Payment failed. You were not charged."); setBusy(""); });
      checkout.open();
    } catch (failure) {
      if (failure instanceof AccountError && failure.status === 401) redirectToSignIn();
      else setError(errorMessage(failure));
      setBusy("");
    }
  }

  async function confirm(result: CheckoutResult) {
    try {
      setWallet(await accountApi<Balance>("/billing/verify", { method: "POST", body: JSON.stringify(result) }));
      setNotice("Payment received. Your credits have been added.");
    } catch (failure) {
      setError(`${errorMessage(failure)} If you were charged, your credits will appear shortly.`);
    } finally { setBusy(""); }
  }

  return <div className="workspace">
    <Link className="report-back" href="/dashboard">← Back to workspace</Link>
    <span className="account-step">Credits</span>
    <h1>{money(wallet.balance_cents)} <span className="billing-balance-label">available</span></h1>
    <p className="account-intro">{account?.user.email || (loading ? "Loading your account…" : "Your Dark account")}
      {" · "}New accounts start with {money(wallet.trial_cents)} free to try Dark.</p>
    {error && <p className="account-error" role="alert">{error}</p>}
    {notice && <p className="billing-notice" role="status">{notice}</p>}
    {loading ? <p role="status">Loading credit packs…</p> : <div className="billing-grid">
      {packs.map(pack => <section key={pack.id} className={`billing-plan${pack.bonus ? " billing-plan-pro" : ""}`}>
        {pack.bonus > 0 && <span className="billing-badge">Get {money(pack.bonus)} free</span>}
        <h2>Recharge {money(pack.price)}</h2>
        <p className="billing-price">{money(pack.credit)}<span> in credits</span></p>
        <ul>
          <li>Pay {money(pack.price)} once, no subscription</li>
          {pack.bonus > 0 && <li>{money(pack.bonus)} bonus credit included</li>}
          <li>Credits never expire</li>
        </ul>
        <button className="button" disabled={Boolean(busy) || !enabled} onClick={() => void buy(pack)}>
          {busy === pack.id ? "Opening checkout…" : `Pay ${money(pack.price)} with Razorpay`}
        </button>
        {!enabled && <p className="billing-until">Payments are not enabled on this server yet.</p>}
      </section>)}
    </div>}
  </div>;
}

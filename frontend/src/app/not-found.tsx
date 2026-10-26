import Link from "next/link";

export default function NotFound() {
  return (
    <main className="not-found">
      <span className="section-label">[ 404 ]</span>
      <h1>Mission not found.</h1>
      <p>This page doesn’t exist. Let’s get you back to building.</p>
      <Link className="button" href="/">
        Back to home
      </Link>
    </main>
  );
}

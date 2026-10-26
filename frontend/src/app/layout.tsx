import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Achilles — Your autonomous dev, always building",
  description:
    "Define the mission once. Achilles reads your codebase, writes the code, runs the tests, and opens the PR.",
  icons: { icon: "/framer/favicon.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

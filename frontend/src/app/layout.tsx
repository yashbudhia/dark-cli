import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dark — Your terminal, now with eyes and hands.",
  description:
    "Dark is an AI agent that edits code, runs commands, and operates real Windows apps: it reads the screen, clicks, types, and tells you what happened.",
  icons: { icon: "/dark-mark.svg" },
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

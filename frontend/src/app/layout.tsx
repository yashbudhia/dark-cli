import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dark — Test the behavior. Keep the proof.",
  description:
    "Inspect native Windows apps, run explicit test scenarios, and save local evidence with Dark.",
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

import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { ClerkTokenBridge } from "@/components/ClerkTokenBridge";
import { Header } from "@/components/Header";
import "./globals.css";

export const metadata: Metadata = {
  title: "SoundCheck — reliability testing for voice agents",
  description:
    "Simulated callers stress-test your voice agent. Latency, barge-in talk-over, and goal completion — gated before you ship.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="min-h-screen">
          <ClerkTokenBridge />
          <Header />
          <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
          <footer className="mx-auto max-w-5xl px-6 pb-12 pt-6 text-sm text-slate-500">
            Open-source reliability gate for voice agents — runs in your CI, comments the
            delta on your PR.
          </footer>
        </body>
      </html>
    </ClerkProvider>
  );
}

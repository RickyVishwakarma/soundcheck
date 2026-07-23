import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SoundCheck — reliability testing for voice agents",
  description:
    "Simulated callers stress-test your voice agent. Latency, barge-in talk-over, and goal completion — gated before you ship.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <span aria-hidden>🔊</span> SoundCheck
            </Link>
            <nav className="flex items-center gap-5 text-sm text-slate-600 dark:text-slate-400">
              <Link href="/" className="hover:text-indigo-600">
                Dashboard
              </Link>
              <a
                href="https://github.com/RickyVishwakarma/soundcheck"
                className="hover:text-indigo-600"
                target="_blank"
                rel="noreferrer"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
        <footer className="mx-auto max-w-5xl px-6 pb-12 pt-6 text-sm text-slate-500">
          Open-source reliability gate for voice agents — runs in your CI, comments the
          delta on your PR.
        </footer>
      </body>
    </html>
  );
}

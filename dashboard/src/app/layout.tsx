import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import { Header } from "@/components/Header";
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
        <AuthProvider>
          <Header />
          <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
          <footer className="mx-auto max-w-5xl px-6 pb-12 pt-6 text-sm text-slate-500">
            Open-source reliability gate for voice agents — runs in your CI, comments the
            delta on your PR.
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}

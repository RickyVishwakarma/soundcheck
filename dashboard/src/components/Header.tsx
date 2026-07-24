"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export function Header() {
  const { email, ready, logout } = useAuth();
  return (
    <header className="border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span aria-hidden>🔊</span> SoundCheck
        </Link>
        <nav className="flex items-center gap-5 text-sm text-slate-600 dark:text-slate-400">
          <Link href="/" className="hover:text-indigo-600">
            Dashboard
          </Link>
          {ready && email ? (
            <>
              <Link href="/settings" className="hover:text-indigo-600">
                Settings
              </Link>
              <span className="hidden text-slate-400 sm:inline">{email}</span>
              <button onClick={logout} className="hover:text-indigo-600">
                Sign out
              </button>
            </>
          ) : ready ? (
            <Link
              href="/login"
              className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500"
            >
              Sign in
            </Link>
          ) : null}
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
  );
}

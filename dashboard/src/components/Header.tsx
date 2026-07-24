import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import Link from "next/link";

/**
 * Server component on purpose: `Show` is server-rendered in @clerk/nextjs v7,
 * so the signed-in/out branches resolve before hydration and the header never
 * flashes the wrong state. The buttons it renders are client components.
 */
export function Header() {
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

          <Show when="signed-in">
            <Link href="/settings" className="hover:text-indigo-600">
              Settings
            </Link>
            <UserButton />
          </Show>

          <Show when="signed-out">
            <SignInButton mode="modal">
              <button className="hover:text-indigo-600">Sign in</button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500">
                Sign up
              </button>
            </SignUpButton>
          </Show>

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

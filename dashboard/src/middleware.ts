import { clerkMiddleware } from "@clerk/nextjs/server";

/**
 * Auth is enforced per page with `auth.protect()`, not here. Clerk deprecated
 * middleware route-matching because it relies on path patterns that can
 * diverge from how Next.js actually routes a request — which both leaves
 * resources reachable and, in our case, made `/` 404.
 */
export default clerkMiddleware();

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
    "/__clerk/:path*",
  ],
};

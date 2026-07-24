import { auth } from "@clerk/nextjs/server";
import { Dashboard } from "@/components/Dashboard";

export default async function Home() {
  // Login-first: signed-out visitors are redirected to sign-in before any
  // dashboard markup is sent. Checked here rather than in middleware because
  // Clerk deprecated route-matcher middleware auth.
  await auth.protect();
  return <Dashboard />;
}

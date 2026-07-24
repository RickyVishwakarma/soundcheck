import { auth } from "@clerk/nextjs/server";
import { Dashboard } from "@/components/Dashboard";

export default async function DashboardPage() {
  await auth.protect();
  return <Dashboard />;
}

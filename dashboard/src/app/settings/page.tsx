import { auth } from "@clerk/nextjs/server";
import { SettingsPanel } from "@/components/SettingsPanel";

export default async function SettingsPage() {
  await auth.protect();
  return <SettingsPanel />;
}

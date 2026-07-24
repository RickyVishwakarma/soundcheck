import { auth } from "@clerk/nextjs/server";
import { RunDetail } from "@/components/RunDetail";

export const dynamic = "force-dynamic";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  await auth.protect();
  const { id } = await params;
  return <RunDetail id={id} />;
}

import { RunReport } from "@/components/account/run-report";

export const metadata = { title: "Run report — Dark" };

export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <RunReport runId={runId} />;
}

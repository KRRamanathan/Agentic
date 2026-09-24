import {
  ApprovalPlayground,
  CostRouterPlayground,
  DebatePlayground,
  EventsPlayground,
  MemoryPlayground,
  OrchestratorPlayground,
  ReactPlayground,
  SelfEvalPlayground,
  StructuredPlayground,
} from "@/components/playgrounds";
import { notFound } from "next/navigation";

const MAP = {
  "structured-output": StructuredPlayground,
  react: ReactPlayground,
  orchestrator: OrchestratorPlayground,
  memory: MemoryPlayground,
  approval: ApprovalPlayground,
  "cost-router": CostRouterPlayground,
  events: EventsPlayground,
  debate: DebatePlayground,
  "self-eval": SelfEvalPlayground,
} as const;

export function generateStaticParams() {
  return Object.keys(MAP).map((slug) => ({ slug }));
}

export default async function PlaygroundPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const View = MAP[slug as keyof typeof MAP];
  if (!View) notFound();
  return <View />;
}

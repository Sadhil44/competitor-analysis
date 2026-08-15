import AskAgentForm from "@/components/AskAgentForm";

export default function AskPage() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ask the agent</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          A LangGraph orchestrator routes your question to a general Q&amp;A, SWOT, or
          developments subagent, grounded in recorded price history, semantic search, and
          live web search. Real LLM calls — expect 30-90 seconds.
        </p>
      </div>
      <AskAgentForm />
    </div>
  );
}

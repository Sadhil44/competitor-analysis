import AskAgentForm from "@/components/AskAgentForm";

export default function AskPage() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ask the agent</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          A LangGraph orchestrator routes each message to a general Q&amp;A, SWOT, or
          developments subagent, grounded in recorded price history, campaigns, and live web
          search — and remembers the conversation, so follow-ups work. Every response shows
          which tools actually grounded it, and SWOT answers are checked against whether the
          analysis was really saved, not just described.
        </p>
      </div>
      <AskAgentForm />
    </div>
  );
}

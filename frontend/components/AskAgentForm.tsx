"use client";

// This is the one client-side fetch in the app — it runs in the browser
// (not inside the Docker network), so it needs the host-mapped API URL
// rather than the Docker-internal one lib/api.ts uses for Server Components.
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const EXAMPLE_QUESTIONS = [
  "What is the recent price history for perennials from Fast Growing Trees?",
  "Give me a SWOT analysis of Holland Bulb Farms.",
  "What's new with American Meadows recently?",
];

const ROUTE_LABEL: Record<string, string> = {
  swot: "SWOT analysis",
  developments: "Developments research",
  general: "Q&A",
};

const TOOL_LABEL: Record<string, string> = {
  query_price_history: "Price history",
  search_developments: "Developments log",
  search_campaigns: "Campaigns log",
  web_search: "Live web search",
  save_swot_analysis: "Saved SWOT",
  save_development: "Saved development",
  save_campaign: "Saved campaign",
};

// react-markdown renders plain HTML elements with no styling of their own
// — mapped onto this app's existing type scale/spacing (no
// @tailwindcss/typography dependency) so headings, bold, lists, and links
// in an agent answer look intentional rather than like a wall of text.
const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <h1 className="mb-2 mt-3 text-base font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-3 text-sm font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-semibold first:mt-0">{children}</h3>,
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ children }) => (
    <code className="rounded bg-black/5 px-1 py-0.5 font-mono text-[0.85em] dark:bg-white/10">{children}</code>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-sky-600 underline underline-offset-2 dark:text-sky-400"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-2 border-zinc-300 pl-3 text-zinc-600 last:mb-0 dark:border-zinc-700 dark:text-zinc-400">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-zinc-200 dark:border-zinc-800" />,
};

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  route?: "swot" | "developments" | "general";
  toolsUsed?: string[];
  saveVerified?: boolean | null;
  failed?: boolean;
}

export default function AskAgentForm() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function ask(q: string) {
    if (!q.trim() || loading) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setQuestion("");
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/agent/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          route: data.route,
          toolsUsed: data.tools_used,
          saveVerified: data.save_verified,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: err instanceof Error ? err.message : "Something went wrong.",
          failed: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    ask(question);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(question);
    }
  }

  function resetConversation() {
    setMessages([]);
    setQuestion("");
    textareaRef.current?.focus();
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex min-h-[28rem] flex-col rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex-1 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <p className="max-w-sm text-sm text-zinc-500 dark:text-zinc-500">
                Ask about pricing, request a SWOT analysis, or check what&apos;s new with a
                competitor. The conversation carries forward, so feel free to ask follow-ups.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => ask(q)}
                    className="rounded-full border border-zinc-300 px-3 py-1 text-xs text-zinc-600 hover:border-zinc-400 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-zinc-500 dark:hover:text-zinc-100"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((m, i) => (
                <ChatBubble key={i} message={m} />
              ))}
              {loading && <TypingBubble />}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="border-t border-zinc-200 p-3 dark:border-zinc-800">
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={messages.length === 0 ? "Ask a question…" : "Ask a follow-up…"}
              rows={1}
              className="max-h-40 min-h-[2.5rem] flex-1 resize-none rounded-lg border border-zinc-300 bg-white p-2.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950 dark:focus:border-zinc-500"
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            >
              {loading ? "…" : "Send"}
            </button>
          </div>
          {messages.length > 0 && (
            <div className="mt-2 flex items-center justify-between">
              <p className="text-xs text-zinc-400">
                Real LLM calls — 10-60s for Q&amp;A, up to several minutes for SWOT/developments
                (each chains multiple research steps before saving).
              </p>
              <button
                type="button"
                onClick={resetConversation}
                className="text-xs text-zinc-500 hover:text-zinc-900 dark:text-zinc-500 dark:hover:text-zinc-100"
              >
                New conversation
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`flex max-w-[85%] flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
        <div
          data-testid={isUser ? "user-message" : "assistant-message"}
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? "whitespace-pre-wrap rounded-br-sm bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
              : message.failed
                ? "whitespace-pre-wrap rounded-bl-sm border border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300"
                : "rounded-bl-sm border border-zinc-200 bg-zinc-50 text-zinc-900 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100"
          }`}
        >
          {isUser || message.failed ? (
            message.content
          ) : (
            <ReactMarkdown components={MARKDOWN_COMPONENTS}>{message.content}</ReactMarkdown>
          )}
        </div>
        {!isUser && !message.failed && (message.route || (message.toolsUsed && message.toolsUsed.length > 0)) && (
          <div className="flex flex-wrap items-center gap-1.5 px-1">
            {message.route && (
              <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-800 dark:bg-sky-900/40 dark:text-sky-300">
                {ROUTE_LABEL[message.route] ?? message.route}
              </span>
            )}
            {message.toolsUsed?.map((tool) => (
              <span
                key={tool}
                className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
              >
                {TOOL_LABEL[tool] ?? tool}
              </span>
            ))}
            {message.saveVerified === true && (
              <span
                title="Confirmed: the agent actually persisted this before finishing"
                className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
              >
                ✓ Verified saved
              </span>
            )}
            {message.saveVerified === false && (
              <span
                title="The agent finished without actually calling the required save tool"
                className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
              >
                ⚠ Not saved
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingBubble() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm border border-zinc-200 bg-zinc-50 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 dark:bg-zinc-600"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";

// react-markdown renders plain HTML elements with no styling of their own
// — mapped onto this app's existing type scale/spacing (no
// @tailwindcss/typography dependency) so headings, bold, lists, and links
// in agent-authored text look intentional rather than like a wall of text.
// Shared by the chat (full block-level content) and the read-only
// SWOT/development/campaign panels below, since both surfaces render raw
// text an LLM produced and neither can assume it's markdown-free — see
// MarkdownText's "inline" variant for the latter.
export const MARKDOWN_COMPONENTS: Components = {
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

// Same inline styling, but paragraphs don't wrap in a <p> — for short,
// single-line agent-authored text (a SWOT bullet, a development summary)
// that's rendered inside an existing <li>/<p> rather than as its own block.
const INLINE_MARKDOWN_COMPONENTS: Components = {
  ...MARKDOWN_COMPONENTS,
  p: ({ children }) => <>{children}</>,
};

// No wrapper element — react-markdown itself renders its output as a plain
// fragment (one <p>/<ul>/etc. per block), so this drops straight into
// whatever container the caller already has (a chat bubble, a <li>).
export default function MarkdownText({
  children,
  variant = "block",
}: {
  children: string;
  variant?: "block" | "inline";
}) {
  return (
    <ReactMarkdown components={variant === "inline" ? INLINE_MARKDOWN_COMPONENTS : MARKDOWN_COMPONENTS}>
      {children}
    </ReactMarkdown>
  );
}

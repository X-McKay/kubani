import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface RichContentProps {
  content: string;
  truncate?: boolean;
  maxLength?: number;
  className?: string;
}

export function RichContent({
  content,
  truncate,
  maxLength = 200,
  className,
}: RichContentProps) {
  const displayContent =
    truncate && content.length > maxLength
      ? content.slice(0, maxLength) + "..."
      : content;

  if (truncate) {
    // Simple text rendering for truncated previews (strip markdown)
    return (
      <span className={cn("text-muted-foreground", className)}>
        {displayContent.replace(/[#*_`~[\]]/g, "")}
      </span>
    );
  }

  return (
    <div
      className={cn(
        "prose prose-invert prose-sm max-w-none",
        "prose-headings:text-foreground prose-headings:font-semibold",
        "prose-p:text-muted-foreground prose-p:leading-relaxed",
        "prose-a:text-primary prose-a:no-underline hover:prose-a:underline",
        "prose-strong:text-foreground",
        "prose-code:text-accent prose-code:bg-muted/50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none",
        "prose-pre:bg-transparent prose-pre:p-0",
        "prose-ul:text-muted-foreground prose-ol:text-muted-foreground",
        "prose-li:marker:text-muted-foreground",
        className
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ children }) => (
            <div className="overflow-x-auto my-3">
              <table className="w-full border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="border-b border-border">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="text-left text-label p-2 border-b border-border-subtle">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="text-body p-2 border-b border-border-subtle/50">
              {children}
            </td>
          ),
          code: ({ className: codeClassName, children, ...props }) => {
            const isInline = !codeClassName;
            if (isInline) {
              return (
                <code
                  className="text-mono bg-muted/50 px-1 py-0.5 rounded text-accent"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn(
                  "block surface-inset p-3 rounded-lg overflow-x-auto text-sm",
                  codeClassName
                )}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="surface-inset p-0 rounded-lg overflow-x-auto my-3">
              {children}
            </pre>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

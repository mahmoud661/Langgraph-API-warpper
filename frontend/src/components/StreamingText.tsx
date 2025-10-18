import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";

interface StreamingTextProps {
  chunks?: string[];
}

export function StreamingText({ chunks = [] }: StreamingTextProps) {
  // Combine all chunks to get the full content
  const fullContent = chunks.join("");

  // Markdown component customization
  const markdownComponents = {
    p: ({ children }: any) => (
      <p className="mb-2 last:mb-0">{children}</p>
    ),
    code: ({ node, inline, className, children, ...props }: any) =>
      inline ? (
        <code className="px-1.5 py-0.5 bg-gray-800 rounded text-sm" {...props}>
          {children}
        </code>
      ) : (
        <pre className="p-3 my-2 overflow-x-auto bg-gray-800 rounded-lg">
          <code className={className} {...props}>
            {children}
          </code>
        </pre>
      ),
    ul: ({ children }: any) => (
      <ul className="my-2 space-y-1 list-disc list-inside">{children}</ul>
    ),
    ol: ({ children }: any) => (
      <ol className="my-2 space-y-1 list-decimal list-inside">{children}</ol>
    ),
    a: ({ href, children }: any) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-gray-300 underline hover:text-white"
      >
        {children}
      </a>
    ),
    h1: ({ children }: any) => (
      <h1 className="mt-4 mb-2 text-2xl font-bold">{children}</h1>
    ),
    h2: ({ children }: any) => (
      <h2 className="mt-3 mb-2 text-xl font-bold">{children}</h2>
    ),
    h3: ({ children }: any) => (
      <h3 className="mt-2 mb-1 text-lg font-bold">{children}</h3>
    ),
  };

  return (
    <div className="prose prose-invert max-w-none streaming-content">
      <AnimatePresence>
        {chunks.map((chunk, index) => (
          <motion.span
            key={index}
            initial={{ opacity: 0, filter: "blur(8px)" }}
            animate={{ opacity: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            style={{
              display: "inline",
              whiteSpace: "pre-wrap",
            }}
          >
            {chunk}
          </motion.span>
        ))}
      </AnimatePresence>
    </div>
  );
}


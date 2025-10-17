import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface StreamingTextProps {
  content: string;
  isStreaming?: boolean;
}

interface Chunk {
  id: number;
  text: string;
}

export function StreamingText({ content, isStreaming }: StreamingTextProps) {
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const previousContentRef = useRef(content);
  const chunkIdRef = useRef(0);

  useEffect(() => {
    if (!isStreaming) {
      setChunks([]);
      previousContentRef.current = content;
      chunkIdRef.current = 0;
      return;
    }

    const previousContent = previousContentRef.current;

    if (content.length < previousContent.length) {
      setChunks(content ? [{ id: chunkIdRef.current++, text: content }] : []);
      previousContentRef.current = content;
      return;
    }

    if (content === previousContent) {
      return;
    }

    if (!content.startsWith(previousContent)) {
      setChunks(content ? [{ id: chunkIdRef.current++, text: content }] : []);
      previousContentRef.current = content;
      return;
    }

    const newText = content.slice(previousContent.length);
    if (newText) {
      setChunks((prev) => [
        ...prev,
        {
          id: chunkIdRef.current++,
          text: newText,
        },
      ]);
      previousContentRef.current = content;
    }
  }, [content, isStreaming]);

  const isStreamingMode = isStreaming && chunks.length > 0;

  if (isStreamingMode) {
    return (
      <div className="prose break-words whitespace-pre-wrap prose-invert max-w-none streaming-content">
        {chunks.map((chunk) => (
          <motion.span
            key={chunk.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1.2, ease: "easeInOut" }}
            className="inline"
          >
            {chunk.text}
          </motion.span>
        ))}
      </div>
    );
  }

  return (
    <motion.div
      className="prose prose-invert max-w-none streaming-content"
      initial={false}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          code: ({ node, inline, className, children, ...props }: any) =>
            inline ? (
              <code
                className="px-1.5 py-0.5 bg-gray-800 rounded text-sm"
                {...props}
              >
                {children}
              </code>
            ) : (
              <pre className="p-3 my-2 overflow-x-auto bg-gray-800 rounded-lg">
                <code className={className} {...props}>
                  {children}
                </code>
              </pre>
            ),
          ul: ({ children }) => (
            <ul className="my-2 space-y-1 list-disc list-inside">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-2 space-y-1 list-decimal list-inside">
              {children}
            </ol>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-300 underline hover:text-white"
            >
              {children}
            </a>
          ),
          h1: ({ children }) => (
            <h1 className="mt-4 mb-2 text-2xl font-bold">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-3 mb-2 text-xl font-bold">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mt-2 mb-1 text-lg font-bold">{children}</h3>
          ),
        }}
      >
        {content || ""}
      </ReactMarkdown>
    </motion.div>
  );
}


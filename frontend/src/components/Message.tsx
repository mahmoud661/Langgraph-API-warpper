import { User, Bot, AlertCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Message as MessageType } from "../types";

interface MessageProps {
  message: MessageType;
}

function Message({ message }: MessageProps) {
  const isUser = message.role === "user";
  const isError = message.isError;

  console.log("Message rendering:", {
    role: message.role,
    content: message.content,
    isStreaming: message.isStreaming,
  });

  return (
    <div className={`flex gap-4 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`
        flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center
        ${
          isUser
            ? "bg-white text-black"
            : isError
            ? "bg-red-600"
            : "bg-gray-800"
        }
      `}
      >
        {isUser ? (
          <User size={20} />
        ) : isError ? (
          <AlertCircle size={20} />
        ) : (
          <Bot size={20} />
        )}
      </div>

      {/* Message Content */}
      <div className={`flex-1 max-w-3xl ${isUser ? "text-right" : ""}`}>
        <div
          className={`
          inline-block px-4 py-3 rounded-lg
          ${
            isUser
              ? "bg-white text-black"
              : isError
              ? "bg-red-900 bg-opacity-30 border border-red-600"
              : "bg-gray-900"
          }
        `}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-invert max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => (
                    <p className="mb-2 last:mb-0">{children}</p>
                  ),
                  code: ({
                    node,
                    inline,
                    className,
                    children,
                    ...props
                  }: any) =>
                    inline ? (
                      <code
                        className="px-1.5 py-0.5 bg-gray-800 rounded text-sm"
                        {...props}
                      >
                        {children}
                      </code>
                    ) : (
                      <pre className="bg-gray-800 p-3 rounded-lg overflow-x-auto my-2">
                        <code className={className} {...props}>
                          {children}
                        </code>
                      </pre>
                    ),
                  ul: ({ children }) => (
                    <ul className="list-disc list-inside my-2 space-y-1">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="list-decimal list-inside my-2 space-y-1">
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
                    <h1 className="text-2xl font-bold mt-4 mb-2">{children}</h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="text-xl font-bold mt-3 mb-2">{children}</h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="text-lg font-bold mt-2 mb-1">{children}</h3>
                  ),
                }}
              >
                {message.content || ""}
              </ReactMarkdown>
              {message.isStreaming && (
                <span className="inline-block w-2 h-4 bg-white animate-pulse ml-1" />
              )}
            </div>
          )}
        </div>
        {message.timestamp && (
          <p className="text-xs text-gray-500 mt-1 px-1">
            {new Date(message.timestamp).toLocaleTimeString()}
          </p>
        )}
      </div>
    </div>
  );
}

export default Message;


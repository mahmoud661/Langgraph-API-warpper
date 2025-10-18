import { User, Bot, AlertCircle } from "lucide-react";
import { StreamingText } from "./StreamingText";
import { Message as MessageType } from "../types";

interface MessageProps {
  message: MessageType;
}

function Message({ message }: MessageProps) {
  const isUser = message.role === "user";
  const isError = message.isError;

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
            <StreamingText chunks={message.chunks} />
          )}
        </div>
        {message.timestamp && (
          <p className="px-1 mt-1 text-xs text-gray-500">
            {new Date(message.timestamp).toLocaleTimeString()}
          </p>
        )}
      </div>
    </div>
  );
}

export default Message;

import Message from "./Message";
import { Message as MessageType } from "../types";

interface MessageListProps {
  messages: MessageType[];
}

function MessageList({ messages }: MessageListProps) {
  console.log(
    "MessageList rendering with messages:",
    messages.length,
    messages
  );

  return (
    <div className="max-w-4xl px-4 py-6 mx-auto space-y-6">
      {messages.map((message, index) => (
        <Message
          key={message.id ?? `${message.timestamp}-${index}`}
          message={message}
        />
      ))}
    </div>
  );
}

export default MessageList;


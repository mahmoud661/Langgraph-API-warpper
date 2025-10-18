import { useState, useEffect, useRef } from "react";
import { Menu, Send, StopCircle } from "lucide-react";
import MessageList from "./MessageList";
import { useWebSocket } from "../hooks/useWebSocket";
import { Message, WebSocketMessage, ChatMessage } from "../types";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

const generateMessageId = () =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

interface ChatInterfaceProps {
  threadId: string | null;
  onThreadCreated: (threadId: string) => void;
  onUpdateThreadTitle: (threadId: string, firstMessage: string) => void;
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
}

interface HistoryMessage {
  role: "user" | "assistant" | "system";
  content: Array<{ data: string }>;
  timestamp: string;
  id: string;
}

function ChatInterface({
  threadId,
  onThreadCreated,
  onUpdateThreadTitle,
  onToggleSidebar,
  sidebarOpen,
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isNewThreadRef = useRef(false);

  const {
    sendMessage: wsSendMessage,
    isConnected,
    connect,
    disconnect,
    cancelStream,
  } = useWebSocket({
    url: `${API_URL.replace("http", "ws")}/ws/chat-stream`,
    onMessage: (data: WebSocketMessage) => handleWebSocketMessage(data),
    onError: (error: Event) => console.error("WebSocket error:", error),
  });

  useEffect(() => {
    connect();
    return () => disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (threadId && !isNewThreadRef.current) {
      loadHistory();
    } else if (!threadId) {
      setMessages([]);
      isNewThreadRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  useEffect(() => {
    const messagesContainer = messagesEndRef.current?.parentElement;
    if (messagesContainer) {
      const isNearBottom =
        messagesContainer.scrollHeight -
          messagesContainer.scrollTop -
          messagesContainer.clientHeight <
        100;

      if (isNearBottom || messages.length === 1) {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    }
  }, [messages]);

  const loadHistory = async () => {
    try {
      const response = await fetch(`${API_URL}/chat/history/${threadId}`);
      if (response.ok) {
        const data = await response.json();
        const formattedMessages: Message[] = data.messages.map(
          (msg: HistoryMessage) => ({
            role: msg.role,
            content: msg.content[0]?.data || "",
            timestamp: msg.timestamp,
            id: msg.id ?? generateMessageId(),
          })
        );
        if (formattedMessages.length > 0) {
          setMessages(formattedMessages);
        }
      }
    } catch (error) {
      console.error("Failed to load history:", error);
    }
  };

  const handleWebSocketMessage = (data: WebSocketMessage) => {
    const eventType = data.event || data.type;

    if (eventType === "message_started") {
      if (data.thread_id && !threadId) {
        isNewThreadRef.current = true;
        onThreadCreated(data.thread_id);
      }

      setIsStreaming(true);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "",
          timestamp: new Date().toISOString(),
          id: data.message_id ?? generateMessageId(),
          chunks: [],
        },
      ]);
    } else if (eventType === "ai_token") {
      const chunk = data.content ?? "";
      if (!chunk) return;

      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant") {
          const updated = [...prev];
          updated[prev.length - 1] = {
            ...last,
            content: last.content + chunk,
            chunks: [...(last.chunks || []), chunk],
          };
          return updated;
        }
        return prev;
      });
    } else if (eventType === "message_complete") {
      setIsStreaming(false);
      isNewThreadRef.current = false;
    } else if (eventType === "error") {
      setIsStreaming(false);
      setMessages((prev) => [
        ...prev,
        {
          role: "system",
          content: `Error: ${data.message || data.error}`,
          timestamp: new Date().toISOString(),
          id: generateMessageId(),
          isError: true,
        },
      ]);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;

    const userMessage: Message = {
      role: "user",
      content: input.trim(),
      timestamp: new Date().toISOString(),
      id: generateMessageId(),
    };

    setMessages((prev) => [...prev, userMessage]);
    const messageContent = input.trim();
    setInput("");

    if (messages.length === 0 && threadId) {
      onUpdateThreadTitle(threadId, messageContent);
    }

    if (!isConnected) {
      try {
        await connect();
        await new Promise((resolve) => setTimeout(resolve, 500));
      } catch (error) {
        console.error("Failed to connect WebSocket:", error);
        return;
      }
    }

    try {
      const chatMessage: ChatMessage = {
        action: "send_message",
        content: [{ type: "text", data: messageContent }],
        thread_id: threadId,
        model: "gemini-2.0-flash-exp",
      };
      wsSendMessage(chatMessage);
    } catch (error) {
      console.error("Failed to send message:", error);
    }
  };

  const handleStop = () => {
    cancelStream();
    setIsStreaming(false);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800">
        {!sidebarOpen && (
          <button
            onClick={onToggleSidebar}
            className="p-1 transition-colors rounded-md hover:bg-gray-800 lg:hidden"
            aria-label="Toggle sidebar"
          >
            <Menu size={18} />
          </button>
        )}
        <div className="flex-1">
          <h1 className="text-sm font-semibold">
            {threadId ? "Chat" : "New Conversation"}
          </h1>
          <div className="flex items-center gap-2 mt-0.5">
            <div
              className={`w-1.5 h-1.5 rounded-full ${
                isConnected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span className="text-xs text-gray-400">
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="max-w-md px-4 text-center">
              <h2 className="mb-4 text-3xl font-bold">GraphFlow Chat</h2>
              <p className="mb-8 text-gray-400">
                Start a conversation with our AI assistant. Ask questions, get
                help, or just chat!
              </p>
              <div className="grid grid-cols-1 gap-3">
                {[
                  "What can you help me with?",
                  "Tell me about LangGraph",
                  "How does streaming work?",
                ].map((suggestion, i) => (
                  <button
                    key={i}
                    onClick={() => setInput(suggestion)}
                    className="px-4 py-3 text-sm text-left transition-colors bg-gray-900 border border-gray-800 rounded-lg hover:bg-gray-800"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <MessageList messages={messages} />
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="px-3 py-3 border-t border-gray-800">
        <div className="max-w-4xl mx-auto">
          <div className="relative flex items-center justify-center gap-2">
            <div className="relative flex-1">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Type your message..."
                className="w-full px-3 py-2 overflow-hidden text-sm bg-gray-900 border border-gray-700 border-none rounded-md resize-none focus:outline-none focus:border-white scrollbar-thin min-h-[40px] max-h-[200px]"
                rows={1}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement;
                  target.style.height = "auto";
                  target.style.height =
                    Math.min(target.scrollHeight, 200) + "px";
                }}
                disabled={isStreaming}
              />
            </div>
            {isStreaming ? (
              <button
                onClick={handleStop}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors bg-red-600 rounded-md hover:bg-red-700"
              >
                <StopCircle size={16} />
                Stop
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className={`px-4 py-2 rounded-md transition-colors flex items-center gap-2 text-sm font-medium ${
                  input.trim()
                    ? "bg-white text-black hover:bg-gray-200"
                    : "bg-gray-800 text-gray-500 cursor-not-allowed"
                }`}
              >
                <Send size={16} />
                Send
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ChatInterface;

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  id?: string;
  isStreaming?: boolean;
  isError?: boolean;
}

export interface Thread {
  id: string;
  title: string;
  createdAt: string;
  messages: Message[];
}

export interface WebSocketMessage {
  event?: string;
  type?: string;
  thread_id?: string;
  content?: string;
  message?: string;
  error?: string;
}

export interface ChatMessage {
  action: string;
  content: Array<{
    type: string;
    data: string;
  }>;
  thread_id?: string | null;
  model: string;
}


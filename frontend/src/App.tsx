import { useState, useEffect } from "react";
import ChatInterface from "./components/ChatInterface";
import Sidebar from "./components/Sidebar";
import { Thread } from "./types";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

interface ThreadResponse {
  thread_id: string;
  title?: string;
  created_at: string;
}

function App() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Load threads from backend on mount
  useEffect(() => {
    loadThreads();
  }, []);

  const loadThreads = async () => {
    try {
      const response = await fetch(`${API_URL}/chat/threads?user_id=default`);
      if (response.ok) {
        const data = await response.json();
        const formattedThreads: Thread[] = data.threads.map(
          (thread: ThreadResponse) => ({
            id: thread.thread_id,
            title: thread.title || "New Chat",
            createdAt: thread.created_at,
            messages: [],
          })
        );
        setThreads(formattedThreads);
      }
    } catch (error) {
      console.error("Failed to load threads:", error);
    }
  };

  const createNewThread = () => {
    // Don't pre-create thread - let backend generate it
    setCurrentThreadId(null);
  };

  const selectThread = (threadId: string) => {
    setCurrentThreadId(threadId);
  };

  const deleteThread = async (threadId: string) => {
    // TODO: Add delete endpoint to backend
    setThreads(threads.filter((t) => t.id !== threadId));
    if (currentThreadId === threadId) {
      setCurrentThreadId(null);
    }
  };

  const updateThreadTitle = (threadId: string, firstMessage: string) => {
    setThreads((prevThreads) => {
      const existingThread = prevThreads.find((t) => t.id === threadId);
      if (existingThread) {
        // Update existing thread
        return prevThreads.map((t) =>
          t.id === threadId
            ? {
                ...t,
                title:
                  firstMessage.substring(0, 50) +
                  (firstMessage.length > 50 ? "..." : ""),
              }
            : t
        );
      } else {
        // Add new thread
        return [
          {
            id: threadId,
            title:
              firstMessage.substring(0, 50) +
              (firstMessage.length > 50 ? "..." : ""),
            createdAt: new Date().toISOString(),
            messages: [],
          },
          ...prevThreads,
        ];
      }
    });
  };

  const handleThreadCreated = (threadId: string) => {
    setCurrentThreadId(threadId);
    // Reload threads to get the new thread in the sidebar
    loadThreads();
  };

  return (
    <div className="flex h-screen bg-black text-white overflow-hidden">
      {/* Sidebar - Always rendered but hidden on mobile when closed */}
      <Sidebar
        threads={threads}
        currentThreadId={currentThreadId}
        onSelectThread={selectThread}
        onNewThread={createNewThread}
        onDeleteThread={deleteThread}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <ChatInterface
          threadId={currentThreadId}
          onThreadCreated={handleThreadCreated}
          onUpdateThreadTitle={updateThreadTitle}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          sidebarOpen={sidebarOpen}
        />
      </div>
    </div>
  );
}

export default App;


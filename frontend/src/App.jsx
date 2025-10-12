import { useState, useEffect } from "react";
import ChatInterface from "./components/ChatInterface";
import Sidebar from "./components/Sidebar";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

function App() {
  const [threads, setThreads] = useState([]);
  const [currentThreadId, setCurrentThreadId] = useState(null);
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
        const formattedThreads = data.threads.map((thread) => ({
          id: thread.thread_id,
          title: thread.title || "New Chat",
          createdAt: thread.created_at,
          messages: [],
        }));
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

  const selectThread = (threadId) => {
    setCurrentThreadId(threadId);
  };

  const deleteThread = async (threadId) => {
    // TODO: Add delete endpoint to backend
    setThreads(threads.filter((t) => t.id !== threadId));
    if (currentThreadId === threadId) {
      setCurrentThreadId(null);
    }
  };

  const updateThreadTitle = (threadId, firstMessage) => {
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

  const handleThreadCreated = (threadId) => {
    setCurrentThreadId(threadId);
  };

  return (
    <div className="flex h-screen bg-black text-white overflow-hidden">
      {/* Sidebar */}
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
      <div className="flex-1 flex flex-col">
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


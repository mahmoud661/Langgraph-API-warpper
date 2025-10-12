import { Trash2, MessageSquarePlus, X } from "lucide-react";
import { Thread } from "../types";

interface SidebarProps {
  threads: Thread[];
  currentThreadId: string | null;
  onSelectThread: (threadId: string) => void;
  onNewThread: () => void;
  onDeleteThread: (threadId: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

function Sidebar({
  threads,
  currentThreadId,
  onSelectThread,
  onNewThread,
  onDeleteThread,
  isOpen,
  onToggle,
}: SidebarProps) {
  return (
    <>
      {/* Overlay for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black bg-opacity-50 lg:hidden"
          onClick={onToggle}
          aria-label="Close sidebar"
        />
      )}

      {/* Sidebar */}
      <div
        className={`
        fixed lg:relative inset-y-0 left-0 z-50 lg:z-0
        w-64 bg-zinc-950 border-r border-gray-800
        transform lg:transform-none transition-transform duration-300 ease-in-out
        ${isOpen ? "translate-x-0" : "-translate-x-full"}
        lg:translate-x-0
        flex flex-col h-full
      `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-3 border-b border-gray-800">
          <h2 className="text-sm font-semibold">Conversations</h2>
          <button
            onClick={onToggle}
            className="p-1 rounded lg:hidden hover:bg-gray-800"
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="p-3">
          <button
            onClick={onNewThread}
            className="flex items-center justify-center w-full gap-2 px-3 py-2 text-sm font-medium text-black transition-colors bg-white rounded-md hover:bg-gray-200"
          >
            <MessageSquarePlus size={18} />
            New Chat
          </button>
        </div>

        {/* Thread List */}
        <div className="flex-1 px-2 overflow-y-auto scrollbar-thin">
          {threads.length === 0 ? (
            <div className="px-3 mt-6 text-center text-gray-500">
              <p className="text-xs">No conversations yet</p>
              <p className="mt-1 text-xs opacity-70">
                Start a new chat to begin
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {threads.map((thread) => (
                <div
                  key={thread.id}
                  className={`
                    group relative flex items-center gap-2 p-2 rounded-md cursor-pointer transition-colors
                    ${
                      currentThreadId === thread.id
                        ? "bg-gray-800 text-white"
                        : "hover:bg-gray-900 text-gray-300"
                    }
                  `}
                  onClick={() => onSelectThread(thread.id)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">
                      {thread.title}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {new Date(thread.createdAt).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteThread(thread.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-600 rounded transition-all"
                    aria-label={`Delete ${thread.title}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-3 py-3 border-t border-gray-800">
          <div className="text-xs text-center text-gray-500">
            <p className="text-xs">GraphFlow Chat v1.0</p>
            <p className="mt-1 text-xs opacity-70">Powered by LangGraph</p>
          </div>
        </div>
      </div>
    </>
  );
}

export default Sidebar;


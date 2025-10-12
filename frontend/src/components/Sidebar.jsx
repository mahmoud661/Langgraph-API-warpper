import { Trash2, MessageSquarePlus, X } from "lucide-react";

function Sidebar({
  threads,
  currentThreadId,
  onSelectThread,
  onNewThread,
  onDeleteThread,
  isOpen,
  onToggle,
}) {
  return (
    <>
      {/* Overlay for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black bg-opacity-50 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar */}
      <div
        className={`
        fixed lg:static inset-y-0 left-0 z-50
        w-72 bg-zinc-950 border-r border-gray-800
        transform transition-transform duration-300 ease-in-out
        ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        flex flex-col
      `}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold">Conversations</h2>
          <button
            onClick={onToggle}
            className="p-1 rounded lg:hidden hover:bg-gray-800"
          >
            <X size={20} />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="p-4">
          <button
            onClick={onNewThread}
            className="flex items-center justify-center w-full gap-2 px-4 py-3 font-medium text-black transition-colors bg-white rounded-lg hover:bg-gray-200"
          >
            <MessageSquarePlus size={20} />
            New Chat
          </button>
        </div>

        {/* Thread List */}
        <div className="flex-1 px-2 overflow-y-auto scrollbar-thin">
          {threads.length === 0 ? (
            <div className="px-4 mt-8 text-center text-gray-500">
              <p className="text-sm">No conversations yet</p>
              <p className="mt-2 text-xs">Start a new chat to begin</p>
            </div>
          ) : (
            <div className="space-y-1">
              {threads.map((thread) => (
                <div
                  key={thread.id}
                  className={`
                    group relative flex items-center gap-2 p-3 rounded-lg cursor-pointer transition-colors
                    ${
                      currentThreadId === thread.id
                        ? "bg-gray-800 text-white"
                        : "hover:bg-gray-900 text-gray-300"
                    }
                  `}
                  onClick={() => onSelectThread(thread.id)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
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
                    className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-600 rounded transition-all"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-800">
          <div className="text-xs text-center text-gray-500">
            <p>GraphFlow Chat v1.0</p>
            <p className="mt-1">Powered by LangGraph</p>
          </div>
        </div>
      </div>
    </>
  );
}

export default Sidebar;


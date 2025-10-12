# GraphFlow Frontend

Modern React frontend for GraphFlow API with real-time streaming chat capabilities.

## Features

- 🎨 Modern black and white minimalist design
- 💬 Real-time streaming chat with WebSocket support
- 📱 Responsive design (mobile & desktop)
- 🔄 Thread management (create, switch, delete)
- ⚡ Fast and smooth animations
- 📝 Markdown support in messages
- 🎯 Auto-reconnection for WebSocket
- 🛑 Stop streaming capability

## Tech Stack

- React 18
- Vite
- Tailwind CSS
- WebSocket
- React Markdown
- Lucide Icons

## Setup

1. Install dependencies:
```bash
npm install
```

2. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` and set your API URL (default: http://localhost:5000)

3. Start development server:
```bash
npm run dev
```

The app will be available at http://localhost:5173

## Build

Build for production:
```bash
npm run build
```

Preview production build:
```bash
npm run preview
```

## Usage

1. Click "New Chat" to start a conversation
2. Type your message and press Enter or click Send
3. Watch as the AI streams its response in real-time
4. Click Stop to cancel an ongoing stream
5. Switch between conversations using the sidebar
6. Delete conversations you no longer need

## Environment Variables

- `VITE_API_URL`: Backend API URL (default: http://localhost:5000)

## Project Structure

```
src/
├── components/
│   ├── ChatInterface.jsx    # Main chat interface
│   ├── Sidebar.jsx          # Thread list sidebar
│   ├── MessageList.jsx      # Message container
│   └── Message.jsx          # Individual message
├── hooks/
│   └── useWebSocket.js      # WebSocket hook
├── App.jsx                  # Root component
├── main.jsx                 # Entry point
└── index.css               # Global styles
```

## Features Explained

### Real-time Streaming
Messages stream token-by-token from the backend using WebSocket connections.

### Thread Management
- Each conversation is a separate thread
- Threads persist in local state
- Auto-title generation from first message

### Responsive Design
- Mobile-first approach
- Collapsible sidebar on mobile
- Optimized for all screen sizes

### Auto-reconnection
WebSocket automatically reconnects on connection loss with exponential backoff.

## License

MIT

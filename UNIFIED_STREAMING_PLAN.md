# 🎯 **Complete Unified Streaming Plan - All Scenarios**

## **📋 Overview**

This document outlines the complete implementation plan for a unified streaming system that handles both regular AI conversations and interactive human-in-the-loop workflows in a single WebSocket endpoint.

### **🎪 Core Objectives**
- **Single endpoint** for all streaming (no separate chat/workflow endpoints)
- **Real-time streaming** of AI responses word-by-word
- **Interactive questions** that stream naturally like AI responses
- **Graceful interrupt handling** with user control (answer, cancel, override)
- **Simple frontend integration** with clear event types
- **Robust error recovery** and state management

---

## **🔄 System Architecture**

### **Current State**
```
❌ Separate Systems:
├── ChatRunner (simple chat)
├── WorkflowRunner (interrupts)
├── Different WebSocket endpoints
└── Complex frontend filtering
```

### **Target State**
```
✅ Unified System:
└── Single WebSocket: /ws/chat
    ├── AI Token Streaming
    ├── Interactive Question Streaming  
    ├── Multiple Choice Options
    ├── User Response Handling
    └── Error Recovery
```

---

## **🎭 Complete Scenario Matrix**

### **🎬 Scenario 1: Normal Chat Flow**

**User Action**: Regular conversational message

**Backend Flow**:
```python
User: "Hello, how are you?"
├─ AI Token Stream: "Hi" "there!" "I'm" "doing" "great!"
└─ Complete
```

**Events Sent**:
```json
{"type": "message_start", "thread_id": "abc123"}
{"type": "ai_token", "content": "Hi"}
{"type": "ai_token", "content": " there!"}
{"type": "ai_token", "content": " I'm"}
{"type": "ai_token", "content": " doing"}
{"type": "ai_token", "content": " great!"}
{"type": "message_complete"}
```

**Frontend State**: 
- Show typing indicator → Stream text character by character → Show complete message

---

### **🎬 Scenario 2: Simple Interrupt Flow**

**User Action**: Message triggers tool usage requiring approval

**Backend Flow**:
```python
User: "Search for information about cats"
├─ AI: "I'll search for that information..."
├─ Tool Interrupt: "Which search engine would you prefer?"
├─ Options: [Google, Bing, DuckDuckGo] 
├─ User Selection: "Google"
├─ Tool Execution: Perform search
└─ AI Response: "Here's what I found about cats..."
```

**Events Sent**:
```json
{"type": "message_start", "thread_id": "abc123"}
{"type": "ai_token", "content": "I'll"}
{"type": "ai_token", "content": " search"}
{"type": "ai_token", "content": " for"}
{"type": "ai_token", "content": " that..."}
{"type": "interrupt_detected", "interrupt_id": "int_123"}
{"type": "question_start", "interrupt_id": "int_123"}
{"type": "question_token", "content": "Which"}
{"type": "question_token", "content": " search"}
{"type": "question_token", "content": " engine"}
{"type": "question_complete", "question": "Which search engine would you prefer?"}
{"type": "options_ready", "options": [
    {"value": "google", "label": "Google"},
    {"value": "bing", "label": "Bing"}, 
    {"value": "duckduckgo", "label": "DuckDuckGo"}
], "interrupt_id": "int_123"}
{"type": "waiting_user_input", "interrupt_id": "int_123"}
```

**Frontend State**:
- Normal streaming → Interrupt detected → Question streaming → Show options → Wait for user

**User Response**:
```javascript
websocket.send({
    action: "resume_interrupt",
    interrupt_id: "int_123", 
    user_response: "google"
});
```

---

### **🎬 Scenario 3: User Cancels Interrupt**

**User Action**: Clicks "Cancel" or "Skip" during pending question

**Backend Flow**:
```python
AI: "Which search engine would you prefer?" [Options shown]
User: Clicks "Cancel"
├─ Send interrupt denial
├─ AI continues without executing tool
└─ AI: "I understand. I can't search without your preference, but I can tell you general information about cats."
```

**Events Sent After Cancel**:
```json
{"type": "interrupt_cancelled", "interrupt_id": "int_123"}
{"type": "ai_token", "content": "I"}
{"type": "ai_token", "content": " understand."}
{"type": "ai_token", "content": " I"}
{"type": "ai_token", "content": " can't"}
{"type": "message_complete"}
```

**Frontend Actions**:
```javascript
// User clicks cancel button
websocket.send({
    action: "cancel_interrupt",
    interrupt_id: "int_123"
});
```

**Frontend State**: Remove options UI → Show cancellation message → Continue normal chat

---

### **🎬 Scenario 4: User Overrides with New Message**

**User Action**: Types new message while question is pending

**Backend Flow**:
```python
AI: "Which search engine would you prefer?" [Options pending]
User: "Actually, forget the search. Tell me about dogs instead"
├─ Cancel all pending interrupts
├─ Clear interrupt state
├─ Start fresh conversation thread
└─ Process new message normally
```

**Events Sent**:
```json
{"type": "interrupts_cleared", "cancelled_ids": ["int_123"]}
{"type": "message_start", "thread_id": "abc123"}
{"type": "ai_token", "content": "Sure!"}
{"type": "ai_token", "content": " Dogs"}
{"type": "ai_token", "content": " are"}
{"type": "message_complete"}
```

**Frontend Actions**:
```javascript
// User types new message while interrupt pending
websocket.send({
    action: "new_message", 
    content: "Actually, forget the search. Tell me about dogs instead",
    clear_interrupts: true
});
```

**Frontend State**: Clear all pending UI elements → Start new message stream

---

### **🎬 Scenario 5: Multiple Interrupts (Chain)**

**User Action**: One tool triggers multiple sequential approvals

**Backend Flow**:
```python
User: "Book a restaurant for dinner"
├─ AI: "I'll help you book a restaurant..."
├─ Interrupt 1: "Which city?" → User: "Paris"
├─ Interrupt 2: "What cuisine preference?" → User: "Italian" 
├─ Interrupt 3: "What date and time?" → User: "Tomorrow at 7 PM"
├─ Interrupt 4: "How many people?" → User: "4 people"
├─ Tool Execution: Book restaurant with all parameters
└─ AI: "Great! I've booked an Italian restaurant in Paris for 4 people tomorrow at 7 PM."
```

**Events Sent**:
```json
// First interrupt
{"type": "interrupt_detected", "interrupt_id": "int_1", "sequence": 1, "total": 4}
{"type": "question_complete", "question": "Which city would you like to dine in?"}
{"type": "options_ready", "options": [...]}

// After user answers, second interrupt  
{"type": "interrupt_resolved", "interrupt_id": "int_1", "response": "Paris"}
{"type": "interrupt_detected", "interrupt_id": "int_2", "sequence": 2, "total": 4}
{"type": "question_complete", "question": "What cuisine would you prefer?"}

// Continue chain...
```

**Frontend State**:
- Show progress indicator: "Step 2 of 4"
- Track interrupt sequence
- Clear previous options when new interrupt arrives
- Maintain conversation context

---

### **🎬 Scenario 6: Connection Drops During Interrupt**

**User Action**: Network issue or browser refresh during pending question

**Backend Flow**:
```python
AI: "Which option would you prefer?" [Connection lost]
├─ WebSocket reconnects
├─ Backend restores thread state
├─ Re-send current interrupt state
├─ Continue from where left off
└─ User can still respond to pending question
```

**Events Sent on Reconnect**:
```json
{"type": "connection_restored", "thread_id": "abc123"}
{"type": "state_sync", "current_state": "waiting_interrupt"}
{"type": "resume_interrupt", 
 "interrupt_id": "int_123", 
 "question": "Which search engine would you prefer?",
 "options": [...]}
{"type": "waiting_user_input", "interrupt_id": "int_123"}
```

**Frontend Behavior**:
- Detect reconnection
- Request state sync
- Restore UI to match backend state
- Show "Connection restored" message

---

### **🎬 Scenario 7: Tool Execution Fails**

**User Action**: User selects option but tool execution encounters error

**Backend Flow**:
```python
User: Selects "Google" for search
├─ Tool starts executing
├─ Tool fails (API timeout, network error, etc.)
├─ AI receives error information
├─ AI explains failure and offers alternatives
└─ Continue conversation gracefully
```

**Events Sent**:
```json
{"type": "tool_executing", "tool_name": "search_tool", "interrupt_id": "int_123"}
{"type": "tool_progress", "message": "Connecting to search API..."}
{"type": "tool_error", 
 "error": "Search API timeout", 
 "interrupt_id": "int_123",
 "retry_available": true}
{"type": "ai_token", "content": "I'm"}
{"type": "ai_token", "content": " sorry,"}
{"type": "ai_token", "content": " the"}
{"type": "ai_token", "content": " search"}
{"type": "ai_token", "content": " failed."}
{"type": "message_complete"}
```

**Frontend State**: Show error message → Offer retry option → Continue conversation

---

### **🎬 Scenario 8: Concurrent Users (Same Thread)**

**User Action**: Multiple users/sessions access same conversation thread

**Backend Flow**:
```python
User A: "Search for cats"
├─ Interrupt: "Which search engine?"
User B: Joins conversation (same thread_id)
├─ User B sees current interrupt state  
├─ Either user can respond to interrupt
├─ First response wins
└─ Both users see the continuation
```

**State Management**:
- Thread-level interrupt state (not session-level)
- Broadcast events to all connected clients for same thread
- Handle race conditions gracefully
- First valid response resolves interrupt

**Events for New Connection**:
```json
{"type": "thread_joined", "thread_id": "abc123", "active_users": 2}
{"type": "state_sync", "pending_interrupts": [...]}
```

---

### **🎬 Scenario 9: Mixed Content Interactive Questions**

**User Action**: Question involves multimedia content (images, files, etc.)

**Backend Flow**:
```python
User: Uploads image "What's in this photo?"
├─ AI analyzes image
├─ AI: "I see multiple objects in this image."
├─ Interrupt: "Which object would you like me to focus on?"
├─ Show interactive image with clickable areas
├─ User clicks on specific object
└─ AI responds about selected object
```

**Events Sent**:
```json
{"type": "image_analysis_start"}
{"type": "ai_token", "content": "I"}
{"type": "ai_token", "content": " see"}
{"type": "interrupt_detected", "interrupt_id": "int_123"}
{"type": "interactive_image", 
 "image_url": "data:image/jpeg;base64,...",
 "click_areas": [
    {"id": "cat", "x": 100, "y": 150, "width": 200, "height": 180, "label": "Cat"},
    {"id": "tree", "x": 300, "y": 50, "width": 150, "height": 300, "label": "Tree"}
 ],
 "interrupt_id": "int_123"}
{"type": "waiting_user_click", "interrupt_id": "int_123"}
```

**User Response**:
```javascript
websocket.send({
    action: "resume_interrupt",
    interrupt_id: "int_123",
    user_response: {type: "click", object_id: "cat"}
});
```

---

### **🎬 Scenario 10: Timeout Handling**

**User Action**: User doesn't respond to interrupt within timeout period

**Backend Flow**:
```python
AI: "Which option?" [30 second timeout]
├─ User doesn't respond within timeout
├─ Auto-cancel interrupt  
├─ AI continues with default behavior
└─ AI: "I'll proceed with the default option since I didn't hear from you."
```

**Events Sent**:
```json
{"type": "interrupt_timeout", "interrupt_id": "int_123"}
{"type": "ai_token", "content": "I'll"}
{"type": "ai_token", "content": " proceed"}
{"type": "message_complete"}
```

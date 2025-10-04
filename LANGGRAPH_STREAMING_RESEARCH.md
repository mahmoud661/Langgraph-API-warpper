# 🔬 LangGraph Streaming Behavior Research

**Date**: October 4, 2025  
**Purpose**: Understanding exact LangGraph streaming mechanics for unified streaming implementation

---

## 📚 Research Summary

Based on comprehensive analysis of LangGraph documentation, this document provides the technical foundation for implementing our unified streaming system that handles both AI responses and interactive human-in-the-loop workflows in a single WebSocket endpoint.

---

## 🌊 LangGraph Stream Modes

LangGraph supports multiple streaming modes that can be used individually or in combination:

| Mode | Description | Data Format | Use Case |
|------|-------------|-------------|----------|
| `"values"` | Full graph state after each step | `dict` with complete state | **Interrupt detection** |
| `"updates"` | Only node updates after each step | `dict` with node changes | Step-by-step progress |
| `"messages"` | LLM tokens + metadata | `(token, metadata)` tuple | **AI response streaming** |
| `"custom"` | User-defined data via StreamWriter | Any JSON serializable | **Interactive questions** |
| `"debug"` | Detailed execution information | Debug objects | Development/troubleshooting |

---

## 🎯 Multi-Mode Streaming Strategy

**Key Discovery**: Use `stream_mode=["messages", "values", "custom"]` to capture everything needed:

```python
async for event_type, chunk in graph.astream(
    input_data,
    config=config,
    stream_mode=["messages", "values", "custom"]
):
    if event_type == "messages":
        # AI token streaming
        token, metadata = chunk
        if token.content:
            yield {
                "type": "ai_token", 
                "content": token.content,
                "node": metadata.get("langgraph_node")
            }
            
    elif event_type == "values":
        # State updates including interrupt detection
        if "__interrupt__" in chunk:
            for interrupt in chunk["__interrupt__"]:
                yield {
                    "type": "interrupt_detected", 
                    "interrupt_id": interrupt.id,
                    "question_data": interrupt.value
                }
                
    elif event_type == "custom":
        # Interactive questions streamed word-by-word
        yield {
            "type": "question_token", 
            "content": chunk
        }
```

---

## 🔄 Interrupt Lifecycle Deep Dive

### 1. **Interrupt Creation**

```python
from langgraph.types import interrupt

def search_tool(query: str):
    # This pauses graph execution and waits for user input
    user_choice = interrupt({
        "question": "Which search engine would you prefer?",
        "options": [
            {"value": "google", "label": "Google"},
            {"value": "bing", "label": "Bing"}, 
            {"value": "duckduckgo", "label": "DuckDuckGo"}
        ],
        "metadata": {"tool": "search", "query": query}
    })
    
    # This code only runs after user responds
    return perform_search(query, user_choice)
```

### 2. **State During Interrupt**

```python
# Graph state when interrupt occurs
state = graph.get_state(config)

# Normal state data continues to exist
print(state.values)  # {"messages": [...], "current_task": "searching"}

# Interrupt information is separate
print(state.interrupts)  # [Interrupt(id="int_123", value={...}, resumable=True)]

# Accessing interrupt details
interrupt_obj = state.interrupts[0]
print(interrupt_obj.id)         # "int_123" - unique identifier
print(interrupt_obj.value)      # {"question": "Which search engine?", "options": [...]}
print(interrupt_obj.resumable)  # True - can be resumed
print(interrupt_obj.ns)         # ["search_tool:uuid"] - node namespace
```

### 3. **Resume with Command**

```python
from langgraph.types import Command

# Resume single interrupt
result = graph.invoke(
    Command(resume="google"), 
    config=config
)

# Resume multiple interrupts (if multiple tools paused simultaneously)
result = graph.invoke(
    Command(resume={
        "int_123": "google",      # First interrupt gets "google"
        "int_456": "approved"     # Second interrupt gets "approved" 
    }), 
    config=config
)

# Resume with complex data
result = graph.invoke(
    Command(resume={
        "search_engine": "google",
        "max_results": 10,
        "safe_search": True
    }), 
    config=config
)
```

---

## ⚡ Critical Behavior Patterns

### **Node Re-execution on Resume**

**Important**: When resuming from interrupt, LangGraph re-executes the **entire node** from the beginning:

```python
def problematic_tool(query: str):
    # ❌ WRONG: This API call happens twice!
    expensive_api_call()  # Called initially AND on resume
    
    user_input = interrupt({"question": "Approve this action?"})
    
    if user_input == "yes":
        return "Approved"
    else:
        return "Denied"

def correct_tool(query: str):
    # ✅ CORRECT: Put expensive operations AFTER interrupt
    user_input = interrupt({"question": "Approve this action?"})
    
    if user_input == "yes":
        expensive_api_call()  # Only called after user approval
        return "Approved"
    else:
        return "Denied"
```

### **Streaming Event Sequence**

Here's the exact sequence of events during a typical interrupt flow:

```python
# Timeline of streaming events:

# 1. Normal AI streaming starts
("messages", ("I'll", metadata))          # → ai_token: "I'll"
("messages", (" help", metadata))         # → ai_token: " help" 
("messages", (" you", metadata))          # → ai_token: " you"
("messages", (" search", metadata))       # → ai_token: " search"

# 2. Tool node executes, interrupt detected
("values", {
    "messages": [...],
    "__interrupt__": [
        Interrupt(
            id="int_123",
            value={"question": "Which search engine?", "options": [...]},
            resumable=True
        )
    ]
})                                        # → interrupt_detected

# 3. Interactive question streams via custom mode (if StreamWriter used)
("custom", "Which")                       # → question_token: "Which"
("custom", " search")                     # → question_token: " search"  
("custom", " engine")                     # → question_token: " engine"
("custom", " would")                      # → question_token: " would"
("custom", " you")                        # → question_token: " you"
("custom", " prefer?")                    # → question_token: " prefer?"

# 4. User responds, graph resumes, AI continues
("messages", ("Using", metadata))         # → ai_token: "Using"
("messages", (" Google", metadata))       # → ai_token: " Google"
("messages", (" to", metadata))           # → ai_token: " to"
("messages", (" search...", metadata))    # → ai_token: " search..."
```

---

## 🛠️ StreamWriter for Interactive Questions

To make questions stream like AI responses, use StreamWriter in tools:

```python
from langgraph.config import get_stream_writer

def interactive_search_tool(query: str):
    writer = get_stream_writer()
    
    # Stream question word-by-word like AI response
    question_parts = [
        "Which", " search", " engine", " would", " you", " prefer", 
        " for", " searching", " about", f" '{query}'?"
    ]
    
    for part in question_parts:
        writer(part)  # Each part streams via "custom" mode
    
    # Now pause for user input
    choice = interrupt({
        "options": [
            {"value": "google", "label": "Google"},
            {"value": "bing", "label": "Bing"},
            {"value": "duckduckgo", "label": "DuckDuckGo"}
        ]
    })
    
    return search_with_engine(query, choice)

def advanced_streaming_tool(data):
    writer = get_stream_writer()
    
    # Can stream any JSON-serializable data
    writer({"type": "progress", "message": "Starting analysis..."})
    writer({"type": "progress", "percentage": 25})
    writer({"type": "progress", "message": "Processing data..."})
    writer({"type": "progress", "percentage": 75})
    
    # Final question
    response = interrupt({
        "question": "Analysis complete. How would you like to proceed?",
        "options": ["save", "continue", "restart"]
    })
    
    return handle_user_choice(response)
```

---

## 📊 State Persistence Requirements

### **Checkpointer is Mandatory**

Interrupts only work with a checkpointer configured:

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

# Option 1: In-memory (development/testing)
checkpointer = InMemorySaver()

# Option 2: SQLite (production)
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")

# Compile graph with checkpointer
graph = builder.compile(checkpointer=checkpointer)
```

### **Thread-based Sessions**

Each conversation needs a unique `thread_id` for state persistence:

```python
# Each user session has unique thread
config = {
    "configurable": {
        "thread_id": f"user_{user_id}_session_{session_id}"
    }
}

# First message - may hit interrupt
result = graph.invoke({"messages": [user_message]}, config=config)

# Check for interrupts
if "__interrupt__" in result:
    # Store interrupt info for user
    store_pending_interrupt(user_id, result["__interrupt__"])

# Later - user responds to interrupt
resume_result = graph.invoke(
    Command(resume=user_response), 
    config=config  # Same thread_id resumes conversation
)
```

---

## 🔍 Metadata and Filtering

### **Message Metadata Structure**

```python
# When streaming with "messages" mode
for token, metadata in graph.astream(input, stream_mode="messages"):
    print(f"Token: {token.content}")
    print(f"Node: {metadata['langgraph_node']}")      # Which node generated this
    print(f"Thread: {metadata['thread_id']}")         # Thread identifier  
    print(f"Step: {metadata['langgraph_step']}")      # Step number in graph
    print(f"Tags: {metadata.get('tags', [])}")        # Custom tags if set
```

### **Filtering by Node**

```python
# Stream only tokens from specific nodes
async for token, metadata in graph.astream(input, stream_mode="messages"):
    node_name = metadata.get("langgraph_node")
    
    if node_name == "ai_responder":
        # Only show AI response tokens
        yield {"type": "ai_token", "content": token.content}
    elif node_name == "tool_executor":
        # Tool execution tokens (if any)
        yield {"type": "tool_token", "content": token.content}
```

### **Custom Tags for LLM Filtering**

```python
from langchain.chat_models import init_chat_model

# Tag different LLMs for filtering
primary_llm = init_chat_model("openai:gpt-4", tags=['primary'])
classifier_llm = init_chat_model("openai:gpt-3.5-turbo", tags=['classifier'])

# Filter streams by LLM type
async for token, metadata in graph.astream(input, stream_mode="messages"):
    if metadata.get("tags") == ["primary"]:
        # Only stream primary LLM responses to user
        yield {"type": "ai_token", "content": token.content}
    elif metadata.get("tags") == ["classifier"]:
        # Log classifier decisions but don't stream to user
        log_classifier_decision(token.content)
```

---

## 🚨 Key Implementation Insights

### **1. Multi-Mode is Essential**
- Single stream modes cannot capture both AI tokens and interrupts
- `["messages", "values", "custom"]` provides complete coverage
- Each mode serves a specific purpose in the unified system

### **2. Interrupt Detection Pattern** 
```python
# Always check for __interrupt__ in values mode
if event_type == "values" and "__interrupt__" in chunk:
    # Graph is paused, user input needed
    handle_interrupts(chunk["__interrupt__"])
```

### **3. StreamWriter Enables Question Streaming**
```python
# Make questions feel like AI responses
writer = get_stream_writer()
for word in question.split():
    writer(word)  # Streams via custom mode
```

### **4. Thread Persistence is Critical**
```python
# Must use same thread_id for resume
config = {"configurable": {"thread_id": session_id}}
graph.invoke(input, config=config)           # Initial
graph.invoke(Command(resume=response), config=config)  # Resume
```

### **5. Avoid Side Effects Before Interrupts**
```python
# ❌ Wrong: Side effect before interrupt
def bad_tool():
    send_email()  # Runs twice: initial + resume!
    user_input = interrupt("Confirm?")
    
# ✅ Correct: Side effect after interrupt  
def good_tool():
    user_input = interrupt("Confirm?")
    if user_input == "yes":
        send_email()  # Only runs once after confirmation
```

---

## 🎯 Unified Streaming Implementation Strategy

Based on this research, our unified streaming system should:

1. **Use multi-mode streaming** to capture all event types
2. **Monitor `__interrupt__` in values** for interrupt detection  
3. **Use StreamWriter** for natural question streaming
4. **Maintain thread persistence** across interrupt cycles
5. **Handle node re-execution** by placing side effects appropriately
6. **Filter by metadata** to control what reaches the frontend

This research provides the solid foundation needed to implement the unified streaming system described in `UNIFIED_STREAMING_PLAN.md`.

---

## 🔗 Related Documentation

- **LangGraph Streaming**: https://langchain-ai.github.io/langgraph/how-tos/streaming/
- **Human-in-the-Loop**: https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/add-human-in-the-loop/
- **Graph Reference**: https://langchain-ai.github.io/langgraph/reference/graphs/
- **Types Reference**: https://langchain-ai.github.io/langgraph/reference/types/
- **Our Implementation Plan**: `UNIFIED_STREAMING_PLAN.md`

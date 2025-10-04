"""
Test Examples for Unified Streaming System

This file demonstrates how to use the new unified streaming system
that handles both AI responses and interactive questions in a single WebSocket endpoint.
"""

import asyncio
import json

import websockets


async def test_basic_conversation():
    """Test basic conversation flow."""

    uri = "ws://localhost:8000/ws/unified-chat"

    async with websockets.connect(uri) as websocket:
        print("🔗 Connected to unified chat system")

        # Wait for connection established event
        response = await websocket.recv()
        event = json.loads(response)
        print(f"📩 {event['event']}: {event['message']}")

        # Send a regular message
        message = {
            "action": "send_message",
            "content": [
                {"type": "text", "data": "Hello! Can you help me with a math problem?"}
            ]
        }

        await websocket.send(json.dumps(message))
        print("📤 Sent message: Hello! Can you help me with a math problem?")

        # Process streaming response
        while True:
            try:
                response = await websocket.recv()
                event = json.loads(response)

                if event['event'] == 'ai_token':
                    print(f"🤖 {event['content']}", end="", flush=True)

                elif event['event'] == 'message_complete':
                    print("\n✅ Message completed")
                    break

                elif event['event'] == 'error':
                    print(f"❌ Error: {event['message']}")
                    break

            except websockets.exceptions.ConnectionClosed:
                print("\n🔌 Connection closed")
                break


async def test_interactive_question():
    """Test interactive question with user choice."""

    uri = "ws://localhost:8000/ws/unified-chat"

    async with websockets.connect(uri) as websocket:
        print("🔗 Connected for interactive test")

        # Skip connection event
        await websocket.recv()

        # Ask for a preference that will trigger interactive tool
        message = {
            "action": "send_message",
            "content": [
                {"type": "text", "data": "Call the preference_selector_tool function with category='search engine' and items=['Google', 'Bing', 'DuckDuckGo']. You must use this tool function."}
            ]
        }

        await websocket.send(json.dumps(message))
        print("📤 Sent: I need to search for information about Python programming...")

        interrupt_id = None

        # Process streaming response until interrupt
        while True:
            try:
                response = await websocket.recv()
                event = json.loads(response)
                print(f"\n🔍 DEBUG Event: {event['event']}")  # Debug line

                if event['event'] == 'ai_token':
                    print(f"🤖 {event['content']}", end="", flush=True)

                elif event['event'] == 'question_token':
                    print(f"❓ {event['content']}", end="", flush=True)

                elif event['event'] == 'interrupt_detected':
                    interrupt_id = event['interrupt_id']
                    question_data = event['question_data']
                    print("\n🛑 Interrupt detected!")
                    print(f"📋 Question: {question_data.get('question', 'No question')}")

                    if 'options' in question_data:
                        print("📝 Options:")
                        for option in question_data['options']:
                            print(f"  - {option['label']} ({option['value']})")

                    # Simulate user choosing Google
                    user_choice = "google"
                    print(f"👤 User selects: {user_choice}")

                    # Resume with user choice
                    resume_message = {
                        "action": "resume_interrupt",
                        "interrupt_id": interrupt_id,
                        "user_response": user_choice
                    }

                    await websocket.send(json.dumps(resume_message))
                    print("📤 Sent resume with user choice")

                elif event['event'] == 'message_complete':
                    print("\n✅ Interactive conversation completed")
                    break

                elif event['event'] == 'error':
                    print(f"\n❌ Error: {event['message']}")
                    break

            except websockets.exceptions.ConnectionClosed:
                print("\n🔌 Connection closed")
                break


async def test_multiple_interrupts():
    """Test handling multiple interrupts in sequence."""

    uri = "ws://localhost:8000/ws/unified-chat"

    async with websockets.connect(uri) as websocket:
        print("🔗 Connected for multiple interrupts test")

        # Skip connection event
        await websocket.recv()

        # Send a complex request that might trigger multiple tools
        message = {
            "action": "send_message",
            "content": [
                {"type": "text", "data": "Please use the preference_selector_tool to ask me which search engine I prefer, then use the interactive_question_tool to ask me what I want to search for."}
            ]
        }

        await websocket.send(json.dumps(message))
        print("📤 Sent complex request with multiple tools")

        interrupt_count = 0

        while True:
            try:
                response = await websocket.recv()
                event = json.loads(response)

                if event['event'] == 'ai_token':
                    print(f"🤖 {event['content']}", end="", flush=True)

                elif event['event'] == 'question_token':
                    print(f"❓ {event['content']}", end="", flush=True)

                elif event['event'] == 'interrupt_detected':
                    interrupt_count += 1
                    interrupt_id = event['interrupt_id']
                    question_data = event['question_data']

                    print(f"\n🛑 Interrupt #{interrupt_count} detected!")
                    print(f"📋 Question: {question_data.get('question', 'No question')}")

                    # Handle different types of interrupts
                    if question_data.get('type') == 'preference_selection':
                        # Preference selection - choose first option
                        options = question_data.get('options', [])
                        if options:
                            user_choice = options[0]['value']
                            print(f"👤 User selects first option: {user_choice}")
                        else:
                            user_choice = "default"

                    elif question_data.get('tool_name'):
                        # Tool approval - approve it
                        user_choice = {"action": "approve"}
                        print("👤 User approves tool execution")

                    else:
                        # Generic response
                        user_choice = "yes"
                        print("👤 User responds: yes")

                    # Resume interrupt
                    resume_message = {
                        "action": "resume_interrupt",
                        "interrupt_id": interrupt_id,
                        "user_response": user_choice
                    }

                    await websocket.send(json.dumps(resume_message))
                    print("📤 Resumed interrupt")

                elif event['event'] == 'message_complete':
                    print(f"\n✅ Complex conversation completed with {interrupt_count} interrupts")
                    break

                elif event['event'] == 'error':
                    print(f"\n❌ Error: {event['message']}")
                    break

            except websockets.exceptions.ConnectionClosed:
                print("\n🔌 Connection closed")
                break


async def test_cancel_interrupt():
    """Test cancelling an interrupt."""

    uri = "ws://localhost:8000/ws/unified-chat"

    async with websockets.connect(uri) as websocket:
        print("🔗 Connected for cancel test")

        # Skip connection event
        await websocket.recv()

        # Send message that will trigger interrupt
        message = {
            "action": "send_message",
            "content": [
                {"type": "text", "data": "Can you ask me a question that I can cancel?"}
            ]
        }

        await websocket.send(json.dumps(message))
        print("📤 Sent: Can you ask me a question that I can cancel?")

        cancelled = False
        followup_sent = False
        message_count = 0

        while True:
            try:
                response = await websocket.recv()
                event = json.loads(response)

                if event['event'] == 'ai_token':
                    print(f"🤖 {event['content']}", end="", flush=True)

                elif event['event'] == 'interrupt_detected':
                    interrupt_id = event['interrupt_id']
                    thread_id = event['thread_id']
                    question_data = event['question_data']

                    print("\n🛑 Interrupt detected!")
                    print(f"📋 Question: {question_data.get('question', 'No question')}")
                    print("👤 User decides to cancel...")

                    # Cancel the interrupt
                    cancel_message = {
                        "action": "cancel_interrupt",
                        "interrupt_id": interrupt_id,
                        "thread_id": thread_id
                    }

                    await websocket.send(json.dumps(cancel_message))
                    print("📤 Sent cancel request")

                elif event['event'] == 'interrupt_cancelled':
                    print(f"🚫 Interrupt cancelled: {event['message']}")
                    cancelled = True

                    # Send a follow-up message to test thread behavior after cancellation
                    if not followup_sent:
                        print("📤 Sending follow-up message after cancellation...")
                        followup_message = {
                            "action": "send_message",
                            "content": [
                                {"type": "text", "data": "Now that we cancelled, can you just say hello?"}
                            ]
                        }
                        await websocket.send(json.dumps(followup_message))
                        print("📤 Sent follow-up: Now that we cancelled, can you just say hello?")
                        followup_sent = True

                elif event['event'] == 'message_complete':
                    message_count += 1
                    print(f"\n✅ Message #{message_count} completed")

                    # If we've completed messages after cancellation, we're done
                    if cancelled and followup_sent and message_count >= 1:
                        print("🎯 Test complete - showing thread behavior after cancellation")
                        break

                elif event['event'] == 'connection_closed':
                    print("\n🔌 Connection closed by server")
                    break

                elif event['event'] == 'error':
                    print(f"\n❌ Error: {event['message']}")
                    # Don't break on error, continue to see what happens

            except websockets.exceptions.ConnectionClosed:
                print("\n🔌 Connection closed")
                break


async def main():
    """Run all test scenarios."""

    print("🧪 Testing Unified Streaming System")
    print("=" * 50)

    try:
        print("\n1️⃣  Testing Basic Conversation")
        await test_basic_conversation()

        print("\n\n2️⃣  Testing Interactive Question")
        await test_interactive_question()

        print("\n\n3️⃣  Testing Multiple Interrupts")
        await test_multiple_interrupts()

        print("\n\n4️⃣  Testing Cancel Interrupt")
        await test_cancel_interrupt()

        print("\n\n🎉 All tests completed!")

    except Exception as e:
        print(f"\n💥 Test failed: {e}")


if __name__ == "__main__":
    # Run the tests
    asyncio.run(main())


"""
Frontend JavaScript Example:

// Connect to unified WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/unified-chat');

let currentThreadId = null;
let pendingInterrupts = {};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.event) {
        case 'connection_established':
            console.log('✅ Connected:', data.message);
            break;
            
        case 'ai_token':
            // Stream AI response character by character
            appendToChat(data.content, 'ai');
            break;
            
        case 'question_token':
            // Stream question character by character
            appendToChat(data.content, 'question');
            break;
            
        case 'interrupt_detected':
            // Show interactive question UI
            showInteractiveQuestion(data.interrupt_id, data.question_data);
            pendingInterrupts[data.interrupt_id] = data.question_data;
            break;
            
        case 'message_complete':
            console.log('✅ Message completed');
            showTypingIndicator(false);
            break;
            
        case 'error':
            console.error('❌ Error:', data.message);
            break;
    }
};

// Send regular message
function sendMessage(content) {
    const message = {
        action: 'send_message',
        content: [{type: 'text', data: content}],
        thread_id: currentThreadId || generateThreadId()
    };
    ws.send(JSON.stringify(message));
    showTypingIndicator(true);
}

// Respond to interactive question
function respondToQuestion(interruptId, response) {
    const message = {
        action: 'resume_interrupt', 
        interrupt_id: interruptId,
        user_response: response
    };
    ws.send(JSON.stringify(message));
    
    // Remove question UI
    hideInteractiveQuestion(interruptId);
    delete pendingInterrupts[interruptId];
}

// Cancel interrupt
function cancelQuestion(interruptId) {
    const message = {
        action: 'cancel_interrupt',
        interrupt_id: interruptId
    };
    ws.send(JSON.stringify(message));
    
    hideInteractiveQuestion(interruptId);
    delete pendingInterrupts[interruptId];
}
"""

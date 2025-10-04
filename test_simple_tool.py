"""Simple tool test to see if AI calls tools at all."""

import asyncio
import json

import websockets


async def test_calculator_tool():
    """Test if AI will call the calculator tool."""

    uri = "ws://localhost:8000/ws/unified-chat"

    async with websockets.connect(uri) as websocket:
        print("🔗 Connected to test calculator tool")

        # Skip connection event
        await websocket.recv()

        # Ask for a calculation that should definitely use the calculator
        message = {
            "action": "send_message",
            "content": [
                {"type": "text", "data": "Calculate 15 * 23 using the calculator_tool function. You must use the tool."}
            ],
            "thread_id": "calc_test_123"
        }

        await websocket.send(json.dumps(message))
        print("📤 Sent: Calculate 15 * 23 using calculator_tool")

        # Process streaming response
        while True:
            try:
                response = await websocket.recv()
                event = json.loads(response)

                print(f"🔍 Event: {event['event']}")

                if event['event'] == 'ai_token':
                    print(f"🤖 {event['content']}", end="", flush=True)

                elif event['event'] == 'message_complete':
                    print("\n✅ Calculation completed")
                    break

                elif event['event'] == 'state_update':
                    print(f"\n📊 State keys: {event.get('state_keys', [])}")

                elif event['event'] == 'error':
                    print(f"\n❌ Error: {event['message']}")
                    break

            except websockets.exceptions.ConnectionClosed:
                print("\n🔌 Connection closed")
                break


if __name__ == "__main__":
    asyncio.run(test_calculator_tool())

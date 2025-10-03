"""Websocket module."""
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/workflow")
async def websocket_workflow(websocket: WebSocket):
    """Websocket Workflow.

        Args:
            websocket: Description of websocket.
        """
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            request_data = json.loads(data)

            runner = websocket.app.state.workflow_runner

            if request_data.get("action") == "run":
                thread_id = request_data.get("thread_id") or str(uuid.uuid4())
                messages = request_data.get("messages", [])

                async for chunk in runner.stream_workflow(
                    input_data={"messages": messages},
                    thread_id=thread_id,
                    stream_mode="messages"
                ):
                    await websocket.send_json(chunk)

            elif request_data.get("action") == "resume":
                thread_id = request_data.get("thread_id")
                resume_value = {
                    "action": request_data.get("resume_action", "approve"),
                    "modified_args": request_data.get("modified_args")
                }

                result = await runner.resume_workflow(thread_id, resume_value)
                await websocket.send_json(result)

            elif request_data.get("action") == "get_state":
                thread_id = request_data.get("thread_id")
                state = await runner.get_state(thread_id)
                await websocket.send_json(state)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"error": str(e)})
        await websocket.close()

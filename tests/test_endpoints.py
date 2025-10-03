"""
Endpoint tests for LangGraph Workflow and Chat API
Tests API structure, validation, and schema compliance
"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test the root endpoint"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "endpoints" in data


@pytest.mark.asyncio
async def test_openapi_schema_available():
    """Test OpenAPI schema accessibility"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "paths" in data
        assert "info" in data


@pytest.mark.asyncio
async def test_chat_endpoints_in_schema():
    """Verify all chat endpoints are registered"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")
        data = response.json()
        paths = data["paths"]

        assert "/chat/send" in paths
        assert "/chat/stream" in paths
        assert "/chat/history/{thread_id}" in paths
        assert "/chat/threads" in paths
        assert "/chat/retry/{thread_id}" in paths
        assert "/chat/checkpoints/{thread_id}" in paths
        assert "/chat/resume/{thread_id}" in paths


@pytest.mark.asyncio
async def test_workflow_endpoints_in_schema():
    """Verify all workflow endpoints are registered"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")
        data = response.json()
        paths = data["paths"]

        assert "/workflow/stream" in paths
        assert "/workflow/resume/{thread_id}" in paths
        assert "/workflow/state/{thread_id}" in paths
        assert "/workflow/history/{thread_id}" in paths


@pytest.mark.asyncio
async def test_chat_send_validation_invalid_type():
    """Test chat endpoint rejects invalid content type"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": [
                    {"type": "invalid_type", "data": "test"}
                ]
            }
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_send_validation_missing_type():
    """Test chat endpoint requires type field"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": [
                    {"data": "test without type"}
                ]
            }
        )
        assert response.status_code in [422, 500]


@pytest.mark.asyncio
async def test_chat_send_validation_missing_data():
    """Test chat endpoint requires data field"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": [
                    {"type": "text"}
                ]
            }
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_image_content_validation():
    """Test image content requires mime_type and source_type"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": [
                    {"type": "image", "data": "test"}
                ]
            }
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_file_content_validation():
    """Test file content requires mime_type and source_type"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": [
                    {"type": "file", "data": "test"}
                ]
            }
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_audio_content_validation():
    """Test audio content requires mime_type and source_type"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": [
                    {"type": "audio", "data": "test"}
                ]
            }
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_workflow_resume_action_validation():
    """Test workflow resume requires valid action"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/workflow/resume/test-thread",
            json={
                "action": "invalid_action"
            }
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_content_array_structure():
    """Test that content must be an array"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": "not an array"
            }
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_valid_text_content_structure():
    """Test valid text content structure passes validation"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": [
                    {"type": "text", "data": "Hello"}
                ]
            }
        )
        assert response.status_code in [200, 500]


@pytest.mark.asyncio
async def test_valid_image_url_structure():
    """Test valid image URL content structure passes validation"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/send",
            json={
                "content": [
                    {
                        "type": "image",
                        "data": "https://example.com/image.jpg",
                        "mime_type": "image/jpeg",
                        "source_type": "url"
                    }
                ]
            }
        )
        assert response.status_code in [200, 500]


@pytest.mark.asyncio
async def test_docs_endpoint():
    """Test API documentation is accessible"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")
        assert response.status_code == 200

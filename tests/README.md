## Testing Guide

This directory contains comprehensive tests for the LangGraph Workflow and Chat API endpoints.

### Test Structure

**`test_endpoints.py`** - Comprehensive endpoint validation tests
- ✅ API structure and registration
- ✅ Input validation for all content types
- ✅ Multimodal content validation (text, image, file, audio)
- ✅ Error handling and edge cases
- ✅ OpenAPI schema compliance

### Running Tests

#### Run All Tests
```bash
pytest tests/ -v
```

#### Run Specific Test
```bash
pytest tests/test_endpoints.py::test_chat_endpoints_in_schema -v
```

#### Run with Coverage
```bash
pytest tests/ --cov=src --cov-report=html
```

### Test Results

**✅ 20 Tests Passing**

#### Chat API Tests (11)
- ✅ Chat endpoints registered in schema
- ✅ Text content validation
- ✅ Image content validation (URL and base64)
- ✅ File content validation  
- ✅ Audio content validation
- ✅ Invalid content type rejection
- ✅ Missing required fields detection
- ✅ Content array structure enforcement

#### Workflow API Tests (5)
- ✅ Workflow endpoints registered in schema
- ✅ Input validation
- ✅ Resume action validation
- ✅ Required fields enforcement

#### General Tests (4)
- ✅ Root endpoint functionality
- ✅ OpenAPI schema availability
- ✅ API documentation accessibility
- ✅ Content structure validation

### What's Tested

#### Content Block Validation ✅
All content types must follow `{type, data}` structure:

**Text Content:**
```json
{"type": "text", "data": "Hello world"}
```

**Image Content:**
```json
{
  "type": "image",
  "data": "https://example.com/image.jpg",
  "mime_type": "image/jpeg",
  "source_type": "url"
}
```

**File Content:**
```json
{
  "type": "file",
  "data": "<base64>",
  "mime_type": "application/pdf",
  "source_type": "base64",
  "filename": "document.pdf"
}
```

**Audio Content:**
```json
{
  "type": "audio",
  "data": "<base64>",
  "mime_type": "audio/wav",
  "source_type": "base64"
}
```

#### Endpoint Coverage ✅

**Chat Endpoints:**
- POST `/chat/send` - Send messages
- POST `/chat/stream` - SSE streaming
- POST `/chat/retry/{thread_id}/{message_index}` - Retry messages
- GET `/chat/history/{thread_id}` - Get history
- GET `/chat/threads` - List threads

**Workflow Endpoints:**
- POST `/workflow/run` - Execute workflow
- POST `/workflow/stream` - Stream workflow
- POST `/workflow/resume/{thread_id}` - Resume with approval
- GET `/workflow/state/{thread_id}` - Get state
- GET `/workflow/history/{thread_id}` - Get checkpoint history

### Test Configuration

- **Framework**: pytest with pytest-asyncio
- **HTTP Client**: httpx AsyncClient with ASGI transport
- **Validation**: Tests run against FastAPI app without requiring live server
- **Speed**: All tests complete in ~2 seconds

### Notes

- Tests validate API structure and input validation
- No actual LLM calls are made (prevents API costs)
- Tests use ASGI transport for direct app testing
- All multimodal content types are validated
- Proper error codes are verified (422 for validation, 500 for server errors)

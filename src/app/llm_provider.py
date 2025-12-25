"""
LLM configuration for Langgraph-API-wrapper using environment variables.

This module provides a flexible LLM provider system supporting multiple providers:
- OpenAI (GPT models)
- Google Gemini
- Google Vertex AI
- Anthropic Claude
- Local models (Ollama/LLaMA)
"""

import json
import logging
import os
from typing import Optional

from langchain_core.language_models import BaseChatModel

# Configure logging
logger = logging.getLogger(__name__)

# Global LLM instance
llm_instance: Optional[BaseChatModel] = None
current_llm_provider: str = os.getenv("DEFAULT_LLM_PROVIDER", "anthropic")


def create_llm(provider: Optional[str] = None) -> BaseChatModel:
    """Create LLM instance based on specified or default provider.

    Args:
        provider: LLM provider name. If None, uses DEFAULT_LLM_PROVIDER from env.
                 Supported: 'openai', 'gemini', 'vertex', 'anthropic', 'ollama'

    Returns:
        Initialized LLM instance

    Raises:
        ValueError: If provider is unsupported or configuration is missing
    """
    global llm_instance, current_llm_provider

    provider = provider or current_llm_provider

    try:
        if provider == "openai":
            llm_instance = _create_openai_llm()
        elif provider == "gemini":
            llm_instance = _create_gemini_llm()
        elif provider == "vertex":
            llm_instance = _create_vertex_llm()
        elif provider == "anthropic":
            llm_instance = _create_anthropic_llm()
        elif provider == "ollama":
            llm_instance = _create_ollama_llm()
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

        current_llm_provider = provider
        logger.info(f"🤖 LLM initialized: {provider.upper()}")
        return llm_instance

    except Exception as e:
        logger.error(f"Failed to create LLM instance for {provider}: {e}")

        # Fallback to Anthropic if other provider fails
        if provider != "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
            logger.info("Falling back to Anthropic Claude")
            return create_llm("anthropic")

        # Fallback to OpenAI if Anthropic not available
        if provider != "openai" and os.getenv("OPENAI_API_KEY"):
            logger.info("Falling back to OpenAI")
            return create_llm("openai")

        raise


def _create_openai_llm() -> BaseChatModel:
    """Create OpenAI LLM instance."""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=api_key,
        temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.0")),
        max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
    )


def _create_gemini_llm() -> BaseChatModel:
    """Create Google Gemini LLM instance."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required"
        )

    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
        google_api_key=api_key,
        temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.5")),
        max_output_tokens=int(os.getenv("GEMINI_MAX_TOKENS", "8192")),
    )


def _create_vertex_llm() -> BaseChatModel:
    """Create Google Vertex AI LLM instance."""
    from google.oauth2 import service_account
    from langchain_google_vertexai import ChatVertexAI

    project = os.getenv("VERTEX_AI_PROJECT") or os.getenv("VERTEX_PROJECT")
    if not project:
        raise ValueError(
            "VERTEX_AI_PROJECT or VERTEX_PROJECT environment variable is required"
        )

    # Initialize credentials if service account JSON is provided
    credentials = None
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        try:
            sa_info = json.loads(service_account_json)
            credentials = service_account.Credentials.from_service_account_info(
                sa_info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            logger.info("✓ Vertex AI credentials loaded from service account JSON")
        except Exception as e:
            logger.warning(f"Failed to initialize Vertex AI credentials: {e}")

    return ChatVertexAI(
        model=os.getenv("VERTEX_AI_MODEL")
        or os.getenv("VERTEX_MODEL", "gemini-1.5-flash"),
        project=project,
        location=os.getenv("VERTEX_AI_LOCATION")
        or os.getenv("VERTEX_LOCATION", "us-central1"),
        temperature=float(
            os.getenv("VERTEX_AI_TEMPERATURE") or os.getenv("VERTEX_TEMPERATURE", "0.5")
        ),
        credentials=credentials,
    )


def _create_anthropic_llm() -> BaseChatModel:
    """Create Anthropic Claude LLM instance."""
    from langchain_anthropic import ChatAnthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    return ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        anthropic_api_key=api_key,
        temperature=float(os.getenv("ANTHROPIC_TEMPERATURE", "0.0")),
        max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "8192")),
    )


def _create_ollama_llm() -> BaseChatModel:
    """Create Ollama (local) LLM instance."""
    from langchain_openai import ChatOpenAI

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    return ChatOpenAI(
        model=model,
        api_key="not-needed",  # Ollama doesn't require API key
        base_url=base_url,
        temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.0")),
        tiktoken_model_name="gpt-3.5-turbo",  # For token counting
    )


def get_llm() -> BaseChatModel:
    """Get or create the current LLM instance.

    Returns:
        Current LLM instance, creating it if necessary
    """
    global llm_instance
    if llm_instance is None:
        llm_instance = create_llm()
    return llm_instance


def switch_provider(provider: str) -> BaseChatModel:
    """Switch to a different LLM provider.

    Args:
        provider: Name of the provider to switch to

    Returns:
        New LLM instance
    """
    global current_llm_provider
    logger.info(f"Switching LLM provider from {current_llm_provider} to {provider}")
    return create_llm(provider)


# Initialize default LLM instance
try:
    llm = get_llm()
except Exception as e:
    logger.warning(f"Failed to initialize default LLM: {e}")
    llm = None


__all__ = [
    "llm",
    "create_llm",
    "get_llm",
    "switch_provider",
    "current_llm_provider",
]

"""Tools module."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from src.domain.models import InterruptPayload


def require_approval(tool_func: Callable) -> Callable:
    """Require Approval.

    Args:
        tool_func: Description of tool_func.

    Returns:
        Description of return value.
    """

    @wraps(tool_func)
    def wrapper(*args, **kwargs):
        """Wrapper.


        Returns:
            Description of return value.
        """

        tool_name = tool_func.__name__
        tool_args = {**kwargs}
        if args:
            tool_args["args"] = args

        payload = InterruptPayload(tool_name=tool_name, tool_args=tool_args, reasoning=f"Tool '{tool_name}' requires human approval before execution")

        resume_data = interrupt(payload.model_dump())

        if resume_data.get("action") == "approve":
            return tool_func(*args, **kwargs)
        elif resume_data.get("action") == "modify":
            modified_args = resume_data.get("modified_args", {})
            return tool_func(**modified_args)
        else:
            return {"status": "denied", "tool": tool_name, "message": "Tool execution denied by user"}

    return wrapper


@require_approval
def search_tool(query: str) -> dict[str, Any]:
    """Search Tool.

    Args:
        query: Description of query.

    Returns:
        Description of return value.
    """

    return {
        "tool": "search",
        "query": query,
        "results": [
            {"title": "Example Result 1", "url": "https://example.com/1"},
            {"title": "Example Result 2", "url": "https://example.com/2"},
        ],
    }


def calculator_tool(expression: str) -> dict[str, Any]:
    """Calculate mathematical expressions.
    
    Use this tool to perform mathematical calculations like addition, subtraction, 
    multiplication, division, and exponentiation.

    Args:
        expression: A mathematical expression to evaluate (e.g., "15 * 23", "2 + 3 * 4")

    Returns:
        Dictionary containing the calculation result
    """

    import ast
    import operator

    allowed_operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}

    def safe_eval(node):
        """Safe Eval.

        Args:
            node: Description of node.

        Returns:
            Description of return value.
        """

        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            else:
                raise ValueError(f"Constant type not allowed: {type(node.value).__name__}")
        elif isinstance(node, ast.BinOp):
            op = allowed_operators.get(type(node.op))  # type: ignore
            if op is None:
                raise ValueError(f"Operator not allowed: {type(node.op).__name__}")
            return op(safe_eval(node.left), safe_eval(node.right))
        elif isinstance(node, ast.UnaryOp):
            op = allowed_operators.get(type(node.op))  # type: ignore
            if op is None:
                raise ValueError(f"Operator not allowed: {type(node.op).__name__}")
            return op(safe_eval(node.operand))
        else:
            raise ValueError(f"Expression type not allowed: {type(node).__name__}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = safe_eval(tree.body)
        return {"tool": "calculator", "expression": expression, "result": result}
    except Exception as e:
        return {"tool": "calculator", "expression": expression, "error": str(e)}


def interactive_question_tool(question: str, options: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Interactive Question Tool - Ask user questions with streaming.
    
    This tool demonstrates the unified streaming approach by:
    1. Streaming the question word-by-word like AI responses
    2. Using interrupt() to pause for user input
    3. Supporting both text input and multiple choice options
    
    Args:
        question: The question to ask the user
        options: Optional list of choice options [{"value": "choice1", "label": "Choice 1"}, ...]
        
    Returns:
        Dictionary containing the user's response
    """
    writer = get_stream_writer()

    # Stream question word-by-word to make it feel like AI response
    question_words = question.split()
    for i, word in enumerate(question_words):
        if i == 0:
            writer(word)  # First word without space
        else:
            writer(f" {word}")  # Add space before subsequent words

    # Prepare interrupt payload
    interrupt_data = {
        "type": "user_question",
        "question": question,
        "requires_response": True
    }

    if options:
        interrupt_data["options"] = options
        interrupt_data["input_type"] = "multiple_choice"
    else:
        interrupt_data["input_type"] = "text"

    # Pause for user input
    user_response = interrupt(interrupt_data)

    return {
        "tool": "interactive_question",
        "question": question,
        "user_response": user_response,
        "timestamp": "now"
    }


def preference_selector_tool(category: str, items: list[str]) -> dict[str, Any]:
    """Preference Selector Tool - Let user choose from options.
    
    Example of a practical interactive tool that asks users to select
    their preference from a list of options.
    
    Args:
        category: Category of the selection (e.g., "search engine", "color theme")
        items: List of available options
        
    Returns:
        Dictionary containing the user's selection
    """
    writer = get_stream_writer()

    # Stream the question naturally
    question_parts = [
        "Which", f" {category}", " would", " you", " prefer?"
    ]

    for part in question_parts:
        writer(part)

    # Convert items to option format
    options = [
        {"value": item.lower().replace(" ", "_"), "label": item}
        for item in items
    ]

    # Pause for user selection
    selection = interrupt({
        "type": "preference_selection",
        "question": f"Which {category} would you prefer?",
        "options": options,
        "input_type": "multiple_choice",
        "category": category
    })

    return {
        "tool": "preference_selector",
        "category": category,
        "available_options": items,
        "user_selection": selection,
        "selected_item": next((opt["label"] for opt in options if opt["value"] == selection), selection)
    }


@require_approval
def enhanced_search_tool(query: str) -> dict[str, Any]:
    """Enhanced Search Tool with engine selection.
    
    This tool demonstrates combining approval workflow with preference selection.
    It first asks for search engine preference, then requires approval.
    
    Args:
        query: Search query string
        
    Returns:
        Dictionary containing search results
    """
    # First, let user choose search engine
    engine_choice = preference_selector_tool(
        "search engine",
        ["Google", "Bing", "DuckDuckGo"]
    )

    selected_engine = engine_choice["selected_item"]

    # Simulate search results based on engine choice
    results = {
        "Google": [
            {"title": f"Google Result for '{query}'", "url": f"https://google.com/search?q={query}"},
            {"title": "Google Academic Result", "url": f"https://scholar.google.com/search?q={query}"}
        ],
        "Bing": [
            {"title": f"Bing Result for '{query}'", "url": f"https://bing.com/search?q={query}"},
            {"title": "Bing News Result", "url": f"https://bing.com/news/search?q={query}"}
        ],
        "DuckDuckGo": [
            {"title": f"DuckDuckGo Result for '{query}'", "url": f"https://duckduckgo.com/?q={query}"},
            {"title": "DuckDuckGo Privacy Result", "url": "https://duckduckgo.com/privacy"}
        ]
    }

    return {
        "tool": "enhanced_search",
        "query": query,
        "search_engine": selected_engine,
        "results": results.get(selected_engine, []),
        "engine_selection": engine_choice
    }


def get_available_tools():
    """Get Available Tools.


    Returns:
        Description of return value.
    """

    return [search_tool, calculator_tool, interactive_question_tool, preference_selector_tool, enhanced_search_tool]

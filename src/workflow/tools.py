from typing import Any, Dict, Callable
from functools import wraps
from langgraph.types import interrupt
from src.domain.entities import InterruptPayload
from datetime import datetime


def require_approval(tool_func: Callable) -> Callable:
    @wraps(tool_func)
    def wrapper(*args, **kwargs):
        tool_name = tool_func.__name__
        tool_args = {**kwargs}
        if args:
            tool_args["args"] = args
        
        payload = InterruptPayload(
            tool_name=tool_name,
            tool_args=tool_args,
            reasoning=f"Tool '{tool_name}' requires human approval before execution"
        )
        
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
def search_tool(query: str) -> Dict[str, Any]:
    return {
        "tool": "search",
        "query": query,
        "results": [
            {"title": "Example Result 1", "url": "https://example.com/1"},
            {"title": "Example Result 2", "url": "https://example.com/2"}
        ]
    }


@require_approval
def calculator_tool(expression: str) -> Dict[str, Any]:
    import ast
    import operator
    
    allowed_operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }
    
    def safe_eval(node):
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
        tree = ast.parse(expression, mode='eval')
        result = safe_eval(tree.body)
        return {"tool": "calculator", "expression": expression, "result": result}
    except Exception as e:
        return {"tool": "calculator", "expression": expression, "error": str(e)}


def get_available_tools():
    return [search_tool, calculator_tool]

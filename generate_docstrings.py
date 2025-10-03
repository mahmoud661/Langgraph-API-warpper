#!/usr/bin/env python3
"""Auto-generate docstrings for Python files."""

import argparse
import ast
import sys
from pathlib import Path


class DocstringGenerator:
    """Generate docstrings for Python code."""

    def __init__(self, style: str = "google"):
        """Init  .

        Args:
            style: Description of style.
        """
        self.style = style

    def generate_module_docstring(self, filename: str) -> str:
        """Generate a module-level docstring."""
        module_name = Path(filename).stem
        return f'"""{module_name.replace("_", " ").title()} module."""'

    def generate_class_docstring(self, node: ast.ClassDef) -> str:
        """Generate a class docstring."""
        return f'"""{node.name} class."""'

    def generate_function_docstring(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Generate a function docstring."""
        args = []
        returns = ""

        # Get function arguments
        for arg in node.args.args:
            if arg.arg != "self":
                args.append(f"        {arg.arg}: Description of {arg.arg}.")

        # Check if function has return annotation or return statements
        if node.returns or any(isinstance(n, ast.Return) and n.value for n in ast.walk(node)):
            returns = "        Description of return value."

        docstring_parts = [f'"""{node.name.replace("_", " ").title()}.']

        if args:
            docstring_parts.extend(["", "    Args:"] + args)

        if returns:
            if not args:
                docstring_parts.append("")
            docstring_parts.extend(["", "    Returns:", returns])

        docstring_parts.append('    """')

        return "\n".join(docstring_parts)

    def add_docstrings_to_file(self, filepath: str) -> str:
        """Add missing docstrings to a Python file."""
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content  # Return original if syntax error

        lines = content.splitlines()
        modifications = []

        # Check for module docstring
        if not ast.get_docstring(tree):
            module_docstring = self.generate_module_docstring(filepath)
            modifications.append((0, 0, module_docstring + "\n"))

        # Walk through all nodes
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not ast.get_docstring(node):
                    if isinstance(node, ast.ClassDef):
                        docstring = self.generate_class_docstring(node)
                    else:
                        docstring = self.generate_function_docstring(node)

                    # Insert after the function/class definition line
                    insert_line = node.lineno
                    indent = "    " * (node.col_offset // 4 + 1)
                    indented_docstring = "\n".join(indent + line if line.strip() else line for line in docstring.split("\n"))
                    modifications.append((insert_line, 0, indented_docstring + "\n"))

        # Apply modifications (in reverse order to maintain line numbers)
        for line_num, _, text in sorted(modifications, reverse=True):
            lines.insert(line_num, text)

        return "\n".join(lines)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Auto-generate Python docstrings")
    parser.add_argument("files", nargs="+", help="Python files to process")
    parser.add_argument("--style", default="google", choices=["google", "numpy", "sphinx"], help="Docstring style")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")

    args = parser.parse_args()

    generator = DocstringGenerator(args.style)

    for filepath in args.files:
        if not filepath.endswith(".py"):
            continue

        try:
            new_content = generator.add_docstrings_to_file(filepath)

            if args.dry_run:
                print(f"=== {filepath} ===")
                print(new_content)
                print()
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                    if not new_content.endswith("\n"):
                        f.write("\n")
                print(f"Updated {filepath}")
        except Exception as e:
            print(f"Error processing {filepath}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()

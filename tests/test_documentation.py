"""Ensure public exported APIs remain documented and fully annotated."""

import ast
import inspect
from pathlib import Path

import coformai


def test_all_public_exports_in_reference_modules_and_documented():
    documented_modules = {"client", "config", "graph", "models", "streaming", "errors"}
    for name in coformai.__all__:
        obj = getattr(coformai, name)
        if inspect.isclass(obj):
            assert obj.__module__.split(".")[-1] in documented_modules
            assert inspect.getdoc(obj), name


def test_public_function_signatures_and_docstrings():
    root = Path(coformai.__file__).parent
    for file in root.glob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) or node.name.startswith("_"):
                continue
            assert ast.get_docstring(node), (file.name, node.name)
            assert node.returns is not None, (file.name, node.name)
            for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                if arg.arg not in {"self", "cls"}:
                    assert arg.annotation is not None, (file.name, node.name, arg.arg)

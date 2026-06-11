"""MDL term: zlib over the minified AST (Decision Log v0.10).

Single program: len(zlib(ast_minify(code))). Ensemble [(weight, code), ...]:
len(zlib(concat of minified members in canonical order)) - shared structure
compresses once, so an ensemble of honest variants pays ~one member while
unrelated junk pays in full. Resolves the MDL-vs-ensemble tension.
"""

import ast
import zlib


def _strip_docstrings(tree: ast.Module) -> ast.Module:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return tree


def ast_minify(code: str) -> str:
    """Normalize a program: parse -> strip docstrings -> unparse.

    Whitespace, comments and docstrings disappear; identifiers stay (renaming
    them would reward obfuscation, not penalize verbosity)."""
    tree = ast.parse(code)
    tree = _strip_docstrings(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def mdl_bytes(submission: str | list[tuple[float, str]]) -> int:
    if isinstance(submission, str):
        payload = ast_minify(submission)
    else:
        members = sorted(ast_minify(code) for _, code in submission)
        payload = "\n".join(members)
    return len(zlib.compress(payload.encode("utf-8"), 9))

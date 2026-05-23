"""Tree-sitter based static analysis for repository graph building."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import tree_sitter_javascript as tsjavascript
    import tree_sitter_python as tspython
    import tree_sitter_typescript as tstypescript
    from tree_sitter import Language, Parser, Query, QueryCursor

    _PY_LANG = Language(tspython.language())
    _JS_LANG = Language(tsjavascript.language())
    _TS_LANG = Language(tstypescript.language_typescript())
    _TSX_LANG = Language(tstypescript.language_tsx())
    TREE_SITTER_AVAILABLE = True
except Exception:
    TREE_SITTER_AVAILABLE = False
    _PY_LANG = None
    _JS_LANG = None
    _TS_LANG = None
    _TSX_LANG = None

_PY_QUERY = """
(import_statement name: (dotted_name) @import)
(import_from_statement module_name: (dotted_name) @import)
(class_definition name: (identifier) @class)
(function_definition name: (identifier) @func)
"""

_JS_QUERY = """
(import_statement source: (string (string_fragment) @import))
(class_declaration name: (identifier) @class)
(function_declaration name: (identifier) @func)
(lexical_declaration (variable_declarator name: (identifier) @func value: (arrow_function)))
"""

_TS_QUERY = """
(import_statement source: (string (string_fragment) @import))
(class_declaration name: (type_identifier) @class)
(function_declaration name: (identifier) @func)
(lexical_declaration (variable_declarator name: (identifier) @func value: (arrow_function)))
"""

_JS_ROUTE_QUERY = """
(call_expression
  function: (member_expression
    property: (property_identifier) @method)
  arguments: (arguments (string (string_fragment) @route)))
"""

_JS_API_CALL_QUERY = """
(call_expression
  function: (identifier) @fn
  arguments: (arguments (string (string_fragment) @route)))
(call_expression
  function: (member_expression
    object: (identifier) @obj
    property: (property_identifier) @method)
  arguments: (arguments (string (string_fragment) @route)))
"""

_PARSER_CACHE: Dict[str, Parser] = {}
_QUERY_CACHE: Dict[str, Query] = {}


def _parser_for(lang: Language) -> Parser:
    key = str(id(lang))
    if key not in _PARSER_CACHE:
        parser = Parser(lang)
        _PARSER_CACHE[key] = parser
    return _PARSER_CACHE[key]


def _query_for(lang: Language, query_str: str) -> Query:
    key = f"{id(lang)}:{hash(query_str)}"
    if key not in _QUERY_CACHE:
        _QUERY_CACHE[key] = Query(lang, query_str)
    return _QUERY_CACHE[key]


def _capture_texts(lang: Language, query_str: str, code: str, capture: str) -> List[str]:
    if not code.strip():
        return []
    parser = _parser_for(lang)
    tree = parser.parse(code.encode("utf-8"))
    query = _query_for(lang, query_str)
    cursor = QueryCursor(query)
    captures = cursor.captures(tree.root_node)
    nodes = captures.get(capture, [])
    return [node.text.decode("utf-8", errors="ignore") for node in nodes]


def _lang_for_suffix(suffix: str) -> Optional[Language]:
    if suffix == ".py":
        return _PY_LANG
    if suffix in {".js", ".jsx"}:
        return _JS_LANG
    if suffix == ".tsx":
        return _TSX_LANG
    if suffix == ".ts":
        return _TS_LANG
    return None


def _query_for_suffix(suffix: str) -> str:
    if suffix in {".ts", ".tsx"}:
        return _TS_QUERY
    return _JS_QUERY


def parse_file_details(code: str, suffix: str) -> Tuple[List[str], List[str], List[str]]:
    """Extract imports, classes, and functions using tree-sitter."""
    if not TREE_SITTER_AVAILABLE:
        return [], [], []

    lang = _lang_for_suffix(suffix)
    if lang is None:
        return [], [], []

    if suffix == ".py":
        imports = _capture_texts(lang, _PY_QUERY, code, "import")
        classes = _capture_texts(lang, _PY_QUERY, code, "class")
        functions = _capture_texts(lang, _PY_QUERY, code, "func")
        return imports, classes, functions

    query = _query_for_suffix(suffix)
    imports = _capture_texts(lang, query, code, "import")
    classes = _capture_texts(lang, query, code, "class")
    functions = [
        name
        for name in _capture_texts(lang, query, code, "func")
        if name not in {"useState", "useEffect", "useMemo", "useCallback", "useRef", "useContext"}
    ]
    return imports, classes, functions


def extract_routes(code: str, suffix: str) -> List[Tuple[str, str]]:
    """Extract HTTP route definitions from source using tree-sitter."""
    if not TREE_SITTER_AVAILABLE or not code.strip():
        return []

    lang = _lang_for_suffix(suffix)
    if lang is None:
        return []

    routes: List[Tuple[str, str]] = []
    if suffix == ".py":
        import re

        for method, route in re.findall(
            r"@(?:app|router)\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]", code
        ):
            routes.append((method.upper(), route))
        return routes

    methods = _capture_texts(lang, _JS_ROUTE_QUERY, code, "method")
    route_paths = _capture_texts(lang, _JS_ROUTE_QUERY, code, "route")
    for method, route in zip(methods, route_paths):
        if method.lower() in {"get", "post", "put", "delete", "patch"}:
            routes.append((method.upper(), route))
    return routes


def extract_api_calls(code: str, suffix: str) -> List[str]:
    """Extract client-side API call paths using tree-sitter."""
    if not TREE_SITTER_AVAILABLE or suffix not in {".js", ".jsx", ".ts", ".tsx"}:
        return []

    lang = _lang_for_suffix(suffix)
    if lang is None:
        return []

    calls: List[str] = []
    fns = _capture_texts(lang, _JS_API_CALL_QUERY, code, "fn")
    routes = _capture_texts(lang, _JS_API_CALL_QUERY, code, "route")
    objs = _capture_texts(lang, _JS_API_CALL_QUERY, code, "obj")
    methods = _capture_texts(lang, _JS_API_CALL_QUERY, code, "method")

    for fn, route in zip(fns, routes):
        if fn == "fetch":
            calls.append(route)

    for obj, method, route in zip(objs, methods, routes):
        if obj == "axios" and method in {"get", "post", "put", "delete", "patch"}:
            calls.append(route)

    # Preserve order while deduplicating
    seen = set()
    unique_calls = []
    for call in calls:
        if call not in seen:
            seen.add(call)
            unique_calls.append(call)
    return unique_calls


def parse_path(path: Path, code: str) -> Tuple[List[str], List[str], List[str]]:
    """Parse a file path + contents, falling back to stdlib AST/regex when needed."""
    suffix = path.suffix

    if TREE_SITTER_AVAILABLE and suffix in {".py", ".js", ".jsx", ".ts", ".tsx"}:
        imports, classes, functions = parse_file_details(code, suffix)
        if imports or classes or functions or code.strip():
            return imports, classes, functions

    # Fallback for unsupported extensions or empty tree-sitter results
    import ast
    import re

    if suffix == ".py":
        imports, classes, functions = [], [], []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    functions.append(node.name)
        except SyntaxError:
            pass
        return imports, classes, functions

    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        import_re = re.compile(
            r"(?:import\s+.*?from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))"
        )
        class_re = re.compile(r"class\s+([a-zA-Z0-9_$]+)")
        func_re = re.compile(
            r"(?:function\s+([a-zA-Z0-9_$]+)|const\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)"
        )
        imports = [m[0] or m[1] for m in import_re.findall(code)]
        classes = class_re.findall(code)
        functions = [m[0] or m[1] for m in func_re.findall(code) if (m[0] or m[1])]
        return imports, classes, functions

    return [], [], []

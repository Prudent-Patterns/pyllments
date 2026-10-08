"""
JSON schema and argument checks from a Python signature, with no dependencies.

A tool is a plain function. Its parameters become the schema the model sees,
and the arguments the model sends are checked against it before the call.
"""

from __future__ import annotations

import inspect
import json
import types
import typing
from typing import Any, Callable

CONTEXT_PARAM_NAMES = frozenset({"context", "invocation_context"})

_PRIMITIVES: dict[Any, dict[str, Any]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    list: {"type": "array"},
    dict: {"type": "object"},
}


def is_context_param(name: str, annotation: Any) -> bool:
    if name in CONTEXT_PARAM_NAMES:
        return True
    if annotation is inspect._empty:
        return False
    if isinstance(annotation, str):
        return annotation.endswith("ToolInvocationContext")
    return getattr(annotation, "__name__", None) == "ToolInvocationContext"


def type_schema(annotation: Any) -> dict[str, Any]:
    """The JSON schema for one annotation; unknown types are unconstrained."""
    if annotation is inspect._empty or annotation is Any:
        return {}
    if annotation in _PRIMITIVES:
        return dict(_PRIMITIVES[annotation])
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Literal:
        return {"enum": list(args)}
    if origin in (typing.Union, types.UnionType):
        members = [a for a in args if a is not type(None)]
        schema = type_schema(members[0]) if len(members) == 1 else {"anyOf": [type_schema(a) for a in members]}
        if len(members) < len(args):
            schema = {"anyOf": [schema, {"type": "null"}]} if "anyOf" not in schema else schema
            if "anyOf" in schema and {"type": "null"} not in schema["anyOf"]:
                schema["anyOf"].append({"type": "null"})
        return schema
    if origin in (list, set, tuple):
        schema: dict[str, Any] = {"type": "array"}
        if args and args[0] is not Ellipsis:
            schema["items"] = type_schema(args[0])
        return schema
    if origin is dict:
        schema = {"type": "object"}
        if len(args) == 2:
            schema["additionalProperties"] = type_schema(args[1])
        return schema
    return {}


def parameters_schema(func: Callable) -> tuple[dict[str, Any], bool]:
    """
    The ``parameters`` schema of a tool function and whether it takes a context.

    Returns
    -------
    tuple[dict, bool]
        An object schema with ``properties`` and ``required``, and True when
        the function accepts an injected ``context`` parameter.
    """
    signature = inspect.signature(func)
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = {}
    properties: dict[str, Any] = {}
    required: list[str] = []
    accepts_context = False
    for name, parameter in signature.parameters.items():
        annotation = hints.get(name, parameter.annotation)
        if is_context_param(name, annotation):
            accepts_context = True
            continue
        schema = type_schema(annotation)
        if parameter.default is not inspect._empty:
            schema["default"] = _json_default(parameter.default)
        else:
            required.append(name)
        properties[name] = schema
    return {"type": "object", "properties": properties, "required": required}, accepts_context


def _json_default(value: Any) -> Any:
    """A default as JSON allows it: tuples and sets become lists, so the schema crosses any boundary."""
    if isinstance(value, (tuple, set, frozenset)):
        return [_json_default(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_default(v) for k, v in value.items()}
    return value


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


def _decode_if_json(value: str, schema: dict[str, Any]) -> Any:
    expected = schema.get("type")
    options = [schema] if expected else schema.get("anyOf", [])
    wants_json = any(o.get("type") in ("array", "object", "integer", "number", "boolean") for o in options)
    if not wants_json:
        return value
    try:
        decoded = json.loads(value)
    except ValueError:
        return value
    return decoded if _matches(decoded, schema) else value


def _matches(value: Any, schema: dict[str, Any]) -> bool:
    if "anyOf" in schema:
        return any(_matches(value, option) for option in schema["anyOf"])
    if "enum" in schema:
        return value in schema["enum"]
    expected = schema.get("type")
    if expected is None:
        return True
    if expected in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _JSON_TYPES[expected])


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any] | None) -> dict[str, Any]:
    """
    Check the model's arguments against the schema and return them.

    Raises
    ------
    ValueError
        Naming the missing, unknown, or mistyped arguments, so the error can be
        handed back to the model as a tool failure it can correct.
    """
    arguments = dict(arguments or {})
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    # Models often send a list or object as the JSON text of one, and spell
    # "not given" as "" or "null" for a parameter they do not use. Read both
    # as what they mean before judging types.
    for name, value in list(arguments.items()):
        if name not in properties or not isinstance(value, str):
            continue
        if name not in required and value.strip().lower() in ("", "null", "none"):
            del arguments[name]
            continue
        arguments[name] = _decode_if_json(value, properties[name])
    missing = [name for name in schema.get("required", []) if name not in arguments]
    unknown = [name for name in arguments if name not in properties]
    wrong = [
        f"{name} (expected {properties[name].get('type') or properties[name].get('enum')})"
        for name, value in arguments.items()
        if name in properties and not _matches(value, properties[name])
    ]
    problems = []
    if missing:
        problems.append(f"missing required argument(s): {', '.join(missing)}")
    if unknown:
        problems.append(f"unknown argument(s): {', '.join(unknown)}")
    if wrong:
        problems.append(f"wrong type for: {', '.join(wrong)}")
    if problems:
        raise ValueError("; ".join(problems))
    return arguments

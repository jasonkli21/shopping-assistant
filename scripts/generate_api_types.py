#!/usr/bin/env python3
"""Generate committed TypeScript transport types from the FastAPI OpenAPI schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "apps" / "api"
OUTPUT = REPOSITORY_ROOT / "packages" / "api-types" / "src" / "index.ts"
sys.path.insert(0, str(API_ROOT / "src"))

from shopping.main import app  # noqa: E402


def render_typescript(openapi: dict[str, Any]) -> str:
    lines = [
        "/**",
        " * Generated from the FastAPI OpenAPI contract.",
        " * Regenerate with `make api-types`; do not edit by hand.",
        " */",
        "",
        "export interface components {",
        "  schemas: {",
    ]
    schemas = openapi.get("components", {}).get("schemas", {})
    for name in sorted(schemas):
        lines.extend(_render_named_schema(name, schemas[name], indent="    "))
    lines.extend(["  };", "}", "", "export interface paths {"])

    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, methods in sorted(openapi.get("paths", {}).items()):
        path_lines = [f'  "{path}": {{']
        for method, operation in sorted(methods.items()):
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            operation_id = operation.get("operationId") or f"{method}_{path}"
            operations.append((operation_id, path, operation))
            path_lines.append(f'    "{method}": operations["{operation_id}"];')
        path_lines.append("  };")
        lines.extend(path_lines)
    lines.extend(["}", "", "export interface operations {"])

    for operation_id, _path, operation in sorted(operations):
        lines.append(f'  "{operation_id}": {{')
        parameters: dict[str, list[dict[str, Any]]] = {}
        for parameter in operation.get("parameters", []):
            parameters.setdefault(parameter["in"], []).append(parameter)
        lines.append("    parameters: {")
        for location in ("path", "query", "header", "cookie"):
            values = parameters.get(location, [])
            if values:
                lines.append(f"      {location}: {{")
                for parameter in sorted(values, key=lambda value: value["name"]):
                    optional = "?" if not parameter.get("required", False) else ""
                    lines.append(
                        f'        "{parameter["name"]}"{optional}: '
                        f"{_ts_type(parameter.get('schema', {}))};"
                    )
                lines.append("      };")
        lines.append("    };")

        request_body = operation.get("requestBody")
        if request_body:
            body_schema = _media_schema(request_body)
            optional = "?" if not request_body.get("required", False) else ""
            lines.append(f"    requestBody{optional}: {{ content: {{")
            lines.append(f'      "application/json": {_ts_type(body_schema)};')
            lines.append("    } };")

        lines.append("    responses: {")
        for status, response in sorted(operation.get("responses", {}).items()):
            lines.append(f'      "{status}": {{ content?: {{')
            content = response.get("content", {})
            if content:
                for media, media_schema in sorted(content.items()):
                    lines.append(f'        "{media}": {_ts_type(media_schema.get("schema", {}))};')
            else:
                lines.append('        "application/json"?: undefined;')
            lines.append("      } };")
        lines.extend(["    };", "  };"])
    lines.extend(["}", ""])
    return "\n".join(lines)


def _render_named_schema(name: str, schema: dict[str, Any], indent: str) -> list[str]:
    if "enum" in schema:
        enum_type = " | ".join(json.dumps(value) for value in schema["enum"])
        return [f"{indent}{name}: {enum_type};"]
    if schema.get("type") != "object" or not schema.get("properties"):
        return [f"{indent}{name}: {_ts_type(schema)};"]
    required = set(schema.get("required", []))
    lines = [f"{indent}{name}: {{"]
    for field_name, field_schema in schema["properties"].items():
        optional = "" if field_name in required else "?"
        lines.append(f'{indent}  "{field_name}"{optional}: {_ts_type(field_schema)};')
    lines.append(f"{indent}}};")
    return lines


def _media_schema(request_body: dict[str, Any]) -> dict[str, Any]:
    content = request_body.get("content", {})
    return content.get("application/json", {}).get("schema", {})


def _ts_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", maxsplit=1)[-1]
        return f'components["schemas"]["{name}"]'
    if "anyOf" in schema or "oneOf" in schema:
        variants = schema.get("anyOf", schema.get("oneOf", []))
        return " | ".join(sorted({_ts_type(item) for item in variants})) or "unknown"
    if "allOf" in schema:
        return " & ".join(_ts_type(item) for item in schema["allOf"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    schema_type = schema.get("type")
    if schema_type == "array":
        return f"Array<{_ts_type(schema.get('items', {}))}>"
    if schema_type == "object":
        properties = schema.get("properties")
        if properties:
            required = set(schema.get("required", []))
            fields = []
            for name, item in properties.items():
                optional = "" if name in required else "?"
                fields.append(f"{json.dumps(name)}{optional}: {_ts_type(item)}")
            return "{ " + "; ".join(fields) + " }"
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"Record<string, {_ts_type(additional)}>"
        return "Record<string, unknown>" if additional is not False else "Record<string, never>"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "string":
        return "string"
    if schema_type == "null":
        return "null"
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated types are stale")
    arguments = parser.parse_args()
    generated = render_typescript(app.openapi())
    if arguments.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != generated:
            print(f"Generated API types are stale; run `make api-types` to update {OUTPUT}")
            return 1
        print(f"Generated API types are current: {OUTPUT.relative_to(REPOSITORY_ROOT)}")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generated)
    print(f"Generated {OUTPUT.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

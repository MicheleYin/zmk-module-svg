"""Validate, preview, and generate LVGL component XML for ZMK status screens."""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__:
    from tools.nice_view_xml_components import expand_screen_file
    from tools.nice_view_xml_assets import DITHER_ALGORITHMS
    from tools.nice_view_xml_codegen import (
        MAX_DYNAMIC_BINDINGS,
        MAX_VISIBLE_ASSETS,
        write_generated,
    )
else:
    from nice_view_xml_components import expand_screen_file
    from nice_view_xml_assets import DITHER_ALGORITHMS
    from nice_view_xml_codegen import (
        MAX_DYNAMIC_BINDINGS,
        MAX_VISIBLE_ASSETS,
        write_generated,
    )


TOOLS_DIR = Path(__file__).parent
ROLES = frozenset({"central", "peripheral"})
STATUS_FIELDS_PATH = TOOLS_DIR / "status_fields.json"
SUPPORTED_DIMENSIONS = {(160, 68), (128, 32)}
LVGL_WIDGET_ATTRIBUTES = frozenset(
    {
        "x",
        "y",
        "width",
        "height",
        "align",
        "styles",
        "flex_flow",
        "flex_grow",
        "hidden",
        "scrollable",
        "clickable",
    }
)


@dataclass(frozen=True)
class WidgetSpec:
    field_types: frozenset[str] | None
    attributes: frozenset[str]


WIDGETS: dict[str, WidgetSpec] = {
    "zmk_status_text": WidgetSpec(
        None,
        frozenset(
            {
                "field",
                "format",
                "role",
                "text",
                "long_mode",
                "font_size",
                "anchor",
                "width",
                "height",
            }
        ),
    ),
    "zmk_status_bar": WidgetSpec(
        frozenset({"integer", "percent"}),
        frozenset({"field", "role", "range_min", "range_max"}),
    ),
    "zmk_status_arc": WidgetSpec(
        frozenset({"integer", "percent"}),
        frozenset({"field", "role", "range_min", "range_max", "radius", "ring_width"}),
    ),
    "zmk_status_when": WidgetSpec(
        frozenset({"boolean", "enum", "integer", "percent", "string", "bitmask"}),
        frozenset({"field", "test", "value", "bit", "role"}),
    ),
}


def load_catalog(path: Path = STATUS_FIELDS_PATH) -> dict[str, dict[str, Any]]:
    document = json.loads(path.read_text())
    if document.get("schema_version") != 1:
        raise ValueError("unsupported status field catalog schema version")
    fields = document.get("fields")
    if not isinstance(fields, list):
        raise ValueError("status field catalog must contain a fields array")

    catalog: dict[str, dict[str, Any]] = {}
    for field in fields:
        field_id = field.get("id")
        if not isinstance(field_id, str) or not field_id:
            raise ValueError("every status field needs a non-empty id")
        if field_id in catalog:
            raise ValueError(f"duplicate status field id: {field_id}")
        catalog[field_id] = field
    return catalog


def _valid_value(field: dict[str, Any], value: str) -> bool:
    field_type = field["type"]
    if field_type == "enum":
        return value in field.get("values", [])
    if field_type == "boolean":
        return value in {"true", "false"}
    if field_type in {"integer", "percent"}:
        if not re.fullmatch(r"-?\d+", value):
            return False
        number = int(value)
        minimum = field.get("minimum", 0)
        maximum = field.get("maximum", 100 if field_type == "percent" else None)
        return number >= minimum and (maximum is None or number <= maximum)
    return field_type == "string"


def _validate_dimensions(
    view: ET.Element, expected_dimensions: tuple[int, int] | None
) -> list[str]:
    errors: list[str] = []
    dimensions = []
    for attribute in ("width", "height"):
        value = view.get(attribute)
        if value is None or not re.fullmatch(r"\d+", value):
            errors.append(f"<view> needs a positive integer {attribute}")
            return errors
        dimensions.append(int(value))

    actual = (dimensions[0], dimensions[1])
    if min(actual) <= 0:
        errors.append("<view> width and height must be positive")
    if actual not in SUPPORTED_DIMENSIONS:
        errors.append(f"unsupported screen dimensions {actual[0]}x{actual[1]}")
    if expected_dimensions is not None and actual != expected_dimensions:
        errors.append(
            f"screen dimensions are {actual[0]}x{actual[1]}, expected "
            f"{expected_dimensions[0]}x{expected_dimensions[1]}"
        )
    return errors


def _validate_when(
    element: ET.Element, field: dict[str, Any], field_id: str
) -> list[str]:
    errors: list[str] = []
    test = element.get("test")
    if test in {"equals", "not_equals"}:
        value = element.get("value")
        if value is None:
            errors.append(f"<zmk_status_when test='{test}'> needs a value")
        elif not _valid_value(field, value):
            errors.append(
                f"<zmk_status_when> value '{value}' is invalid for field '{field_id}'"
            )
    elif test in {"bit_set", "bit_clear"}:
        bit = element.get("bit")
        if field["type"] != "bitmask":
            errors.append(f"<zmk_status_when test='{test}'> requires a bitmask field")
        if bit is None or not re.fullmatch(r"\d+", bit):
            errors.append(f"<zmk_status_when test='{test}'> needs a bit index")
        elif int(bit) >= max(1, field.get("maximum", 0).bit_length()):
            errors.append(f"<zmk_status_when> bit {bit} is outside field '{field_id}'")
    else:
        errors.append(
            "<zmk_status_when> test must be equals, not_equals, bit_set, or bit_clear"
        )
    return errors


def _validate_widget(
    element: ET.Element, fields: dict[str, dict[str, Any]]
) -> list[str]:
    widget = WIDGETS.get(element.tag)
    if widget is None:
        return []

    errors = []
    unknown_attributes = {
        attribute
        for attribute in element.attrib
        if attribute not in widget.attributes
        and attribute not in LVGL_WIDGET_ATTRIBUTES
        and not attribute.startswith("style_")
    }
    if unknown_attributes:
        errors.append(
            f"<{element.tag}> has unsupported attributes: "
            f"{', '.join(sorted(unknown_attributes))}"
        )

    field_id = element.get("field")
    if not field_id:
        return errors + [f"<{element.tag}> needs a field attribute"]
    field = fields.get(field_id)
    if field is None:
        return errors + [f"<{element.tag}> references unknown field '{field_id}'"]

    if widget.field_types is not None and field["type"] not in widget.field_types:
        errors.append(f"<{element.tag}> cannot bind {field['type']} field '{field_id}'")
    role = element.get("role")
    if role is not None and role not in field.get("available_on", []):
        errors.append(
            f"<{element.tag}> field '{field_id}' is not available on role '{role}'"
        )

    if element.tag == "zmk_status_text":
        text_format = element.get("format", "text")
        if text_format not in {"text", "percent", "output-label", "profile-number"}:
            errors.append(f"<zmk_status_text> has unsupported format '{text_format}'")
        elif text_format == "percent" and field["type"] != "percent":
            errors.append(
                f"<zmk_status_text> percent format requires a percent field, got '{field_id}'"
            )
    elif element.tag == "zmk_status_when":
        errors.extend(_validate_when(element, field, field_id))
    return errors


def validate_screen_text(
    xml_text: str,
    fields: dict[str, dict[str, Any]],
    expected_dimensions: tuple[int, int] | None = None,
) -> list[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        return [f"invalid XML: {error}"]

    if root.tag != "component":
        return ["root element must be <component>"]

    views = root.findall("view")
    if len(views) != 1:
        return ["component must contain exactly one direct <view>"]

    errors = _validate_dimensions(views[0], expected_dimensions)
    binding_count = 0
    visible_image_count = 0
    parents = {child: parent for parent in root.iter() for child in parent}
    for element in root.iter():
        if element.tag == "zmk_include":
            errors.append("<zmk_include> must be expanded from a screen file")
        if element.tag in WIDGETS:
            binding_count += 1
        if element.tag == "lv_image":
            src = element.get("src")
            if not src:
                errors.append("<lv_image> needs a src attribute")
            dither = element.get("dither")
            if dither is not None and dither not in DITHER_ALGORITHMS:
                errors.append(
                    f"<lv_image> has unsupported dither '{dither}'; choose from "
                    f"{', '.join(DITHER_ALGORITHMS)}"
                )
            parent = parents.get(element)
            if parent is not None and parent.tag == "zmk_status_when":
                visible_image_count += 1
                if element.get("width") is None or element.get("height") is None:
                    errors.append(
                        "<lv_image> under <zmk_status_when> should set width and height"
                    )
        if element.tag == "zmk_status_when":
            children = [
                node for node in element if node.tag in {"lv_label", "lv_image"}
            ]
            if not children:
                errors.append(
                    "<zmk_status_when> needs a nested <lv_label> or <lv_image>"
                )
        errors.extend(_validate_widget(element, fields))
    if visible_image_count > MAX_VISIBLE_ASSETS:
        errors.append(
            f"screen has {visible_image_count} visible image assets; "
            f"budget is {MAX_VISIBLE_ASSETS}"
        )
    if binding_count > MAX_DYNAMIC_BINDINGS:
        errors.append(
            f"screen has {binding_count} dynamic bindings; budget is {MAX_DYNAMIC_BINDINGS}"
        )
    return errors


def validate_screen(
    path: Path, expected_dimensions: tuple[int, int] | None = None
) -> list[str]:
    try:
        xml_text = expand_screen_file(path)
    except ValueError as error:
        return [str(error)]
    errors = validate_screen_text(xml_text, load_catalog(), expected_dimensions)
    # Resolve image paths relative to the screen file when validating on disk.
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return errors
    for element in root.iter("lv_image"):
        src = element.get("src")
        if not src:
            continue
        candidates = [(path.parent / src).resolve(), (Path.cwd() / src).resolve()]
        if not any(candidate.exists() for candidate in candidates):
            errors.append(f"<lv_image> src not found: {src}")
    return errors


def generate(
    screen: Path, output_dir: Path, dither_override: str | None = None
) -> None:
    errors = validate_screen(screen)
    if errors:
        raise ValueError("\n".join(errors))
    header_path, source_path = write_generated(
        screen, output_dir, expand_screen_file(screen), dither_override
    )
    print(f"Generated {header_path}")
    print(f"Generated {source_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate component XML")
    validate_parser.add_argument("screen", type=Path)
    validate_parser.add_argument("--width", type=int)
    validate_parser.add_argument("--height", type=int)

    generate_parser = subparsers.add_parser(
        "generate", help="generate status_screen_gen.c and .h"
    )
    generate_parser.add_argument("screen", type=Path)
    generate_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory for status_screen_gen.c/h",
    )
    generate_parser.add_argument(
        "--dither",
        choices=DITHER_ALGORITHMS,
        help="override dithering for every referenced image and GIF",
    )

    preview_parser = subparsers.add_parser(
        "preview", help="render a PNG using expanded LVGL XML preview data"
    )
    preview_parser.add_argument("screen", type=Path)
    preview_parser.add_argument("--values", type=Path, required=True)
    preview_parser.add_argument(
        "--role", choices=["central", "peripheral"], required=True
    )
    preview_parser.add_argument("--output", type=Path, required=True)
    preview_parser.add_argument("--dither", choices=DITHER_ALGORITHMS)

    args = parser.parse_args(argv)
    if (
        getattr(args, "width", None) is not None
        and getattr(args, "height", None) is None
    ):
        parser.error("--width and --height must be provided together")

    try:
        if args.command == "validate":
            expected_dimensions = (
                (args.width, args.height)
                if getattr(args, "width", None) is not None
                else None
            )
            errors = validate_screen(args.screen, expected_dimensions)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print(f"[OK] {args.screen}")
            return 0
        if args.command == "generate":
            generate(args.screen, args.output_dir, args.dither)
            return 0
        if __package__:
            from tools.nice_view_xml_preview import preview_png, preview_xml_text
        else:
            from nice_view_xml_preview import preview_png, preview_xml_text

        values = json.loads(args.values.read_text()).get("values", {})
        xml = preview_xml_text(
            expand_screen_file(args.screen),
            load_catalog(),
            values,
            args.role,
        )
        preview_png(xml, args.output, args.screen, args.dither)
        print(f"Rendered {args.output}")
        return 0
    except (OSError, TypeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Expand ZMK status XML into static LVGL XML and rasterize a preview PNG."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

if __package__:
    from tools.nice_view_xml import validate_screen_text
    from tools.nice_view_xml_assets import preview_rgba_image
else:
    from nice_view_xml import validate_screen_text
    from nice_view_xml_assets import preview_rgba_image

ROLES = frozenset({"central", "peripheral"})

PREVIEW_WIDTH = 160
PREVIEW_HEIGHT = 68


def _default_value(field: dict[str, Any]) -> Any:
    field_type = field["type"]
    if field_type == "enum":
        return field["values"][0]
    if field_type == "boolean":
        return False
    if field_type == "bitmask":
        return 0
    if field_type == "string":
        return field.get("default", "")
    return field.get("minimum", 0)


def _format_value(value: Any, field: dict[str, Any], fmt: str) -> str:
    if value is None:
        return "--"
    if fmt == "output-label":
        return {"usb": "USB", "ble": "BLE", "none": "--"}.get(
            str(value), str(value)
        )
    if fmt == "profile-number":
        profile_index = int(value)
        return str(profile_index + 1) if profile_index >= 0 else "-"
    if fmt == "percent" and field["type"] == "percent":
        return f"{value}%"
    if field["type"] == "boolean":
        return "true" if value else "false"
    if field["type"] == "enum":
        return str(value)
    return str(value)


def _matches(field: dict[str, Any], element: ET.Element, value: Any) -> bool:
    test = element.get("test")
    if test in {"equals", "not_equals"}:
        expected = element.get("value", "")
        actual = str(value).lower() if field["type"] == "boolean" else str(value)
        matched = actual == expected
        return matched if test == "equals" else not matched
    if test == "bit_set":
        bit = int(element.get("bit", "0"))
        return bool(int(value) & (1 << bit))
    if test == "bit_clear":
        bit = int(element.get("bit", "0"))
        return not bool(int(value) & (1 << bit))
    return False


def preview_xml_text(
    xml_text: str,
    fields: dict[str, dict[str, Any]],
    values: dict[str, Any],
    role: str,
) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown display role: {role}")
    errors = validate_screen_text(xml_text, fields)
    if errors:
        raise ValueError("\n".join(errors))

    root = ET.fromstring(xml_text)
    view = root.find(".//view")
    screen_width = (
        _coord(view, "width", PREVIEW_WIDTH) if view is not None else PREVIEW_WIDTH
    )
    for element in list(root.iter()):
        field_id = element.get("field")
        if element.tag == "zmk_status_text" and field_id:
            field = fields[field_id]
            if role not in field.get("available_on", []):
                element.tag = "lv_obj"
                element.attrib.clear()
                element.set("hidden", "true")
                continue
            text = _format_value(
                values.get(field_id), field, element.get("format", "text")
            )
            attributes = {
                name: value
                for name, value in element.attrib.items()
                if name not in {"field", "format", "font_size", "role", "anchor"}
            }
            font_size = _coord(
                element, "font_size", 11 if element.get("format") == "percent" else 10
            )
            x = _coord(element, "x")
            y = _coord(element, "y")
            width = _coord(element, "width")
            height = _coord(element, "height")
            anchor = element.get("anchor", "start")
            alignment = "left"
            if width > 0:
                line_height = 24 if font_size >= 16 else 14 if font_size > 8 else 8
                if height > 0:
                    y += max((height - line_height) // 2, 0)
                if anchor == "middle":
                    alignment = "center"
                elif anchor == "end":
                    alignment = "right"
            else:
                if anchor == "middle":
                    x -= screen_width // 2
                    alignment = "center"
                elif anchor == "end":
                    x -= screen_width
                    alignment = "right"
            element.tag = "lv_label"
            element.attrib.clear()
            element.attrib.update(attributes)
            element.set("text", text)
            element.set("x", str(x))
            element.set("y", str(y if width > 0 else y - font_size))
            element.set("width", str(width if width > 0 else screen_width))
            element.set("height", str(height if height > 0 else max(font_size + 2, 10)))
            element.set("style_text_align", alignment)
            element.set("style_text_font", _preview_font(font_size, monospace=True))
        elif element.tag == "lv_label" and element.get("text") is not None:
            font_size = _coord(element, "font_size", 10)
            monospace = element.get("font_family") == "monospace"
            element.attrib.pop("font_size", None)
            element.attrib.pop("font_family", None)
            element.set(
                "style_text_font", _preview_font(font_size, monospace=monospace)
            )
        elif element.tag == "zmk_status_bar" and field_id:
            field = fields[field_id]
            percent = values.get(field_id, 0)
            try:
                percent = max(0, min(100, int(percent)))
            except (TypeError, ValueError):
                percent = 0
            width = int(element.get("width", "10"))
            height = int(element.get("height", "4"))
            x = int(element.get("x", "0"))
            y = int(element.get("y", "0"))
            element.tag = "lv_obj"
            element.attrib.clear()
            element.set("x", str(x))
            element.set("y", str(y))
            element.set("width", str(max(1, width * percent // 100)))
            element.set("height", str(height))
            element.set("style_bg_color", "0x000000")
        elif element.tag == "zmk_status_when" and field_id:
            field = fields[field_id]
            value = values.get(field_id, _default_value(field))
            if not _matches(field, element, value):
                parent = next(
                    (node for node in root.iter() if element in list(node)), None
                )
                if parent is not None:
                    parent.remove(element)
                continue
            children = list(element)
            if not children:
                continue
            child = children[0]
            child.attrib.update(
                {
                    key: value
                    for key, value in element.attrib.items()
                    if key not in child.attrib
                }
            )
            element.tag = child.tag
            element.attrib.clear()
            element.attrib.update(child.attrib)
            element[:] = list(child)
        elif element.tag in {"zmk_status_bar", "zmk_status_arc", "zmk_status_when"}:
            element.tag = "lv_obj"
            element.attrib.clear()
            element.set("hidden", "true")

    return ET.tostring(root, encoding="unicode")


def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        raise RuntimeError(
            "preview requires Pillow; run with uv and tools/requirements.txt"
        ) from error
    return Image, ImageDraw, ImageFont


def _coord(element: ET.Element, name: str, default: int = 0) -> int:
    value = element.get(name)
    if value is None or not re.fullmatch(r"-?\d+", value):
        return default
    return int(value)


def _preview_font(font_size: int, monospace: bool = False) -> str:
    if font_size >= 16:
        return "lv_montserrat_20"
    if font_size > 8:
        return "lv_montserrat_12"
    return "lv_unscii_8" if monospace else "lv_montserrat_8"


def _is_hidden(element: ET.Element) -> bool:
    return element.get("hidden") in {"true", "1"}


def _collect_drawables(
    element: ET.Element,
    origin_x: int,
    origin_y: int,
    labels: list[tuple[int, int, int, int, str, str]],
    bars: list[tuple[int, int, int, int]],
) -> None:
    if _is_hidden(element):
        return

    local_x = _coord(element, "x")
    local_y = _coord(element, "y")
    screen_x = origin_x + local_x
    screen_y = origin_y + local_y

    if element.tag == "lv_image":
        return

    if element.tag == "lv_label":
        text = element.get("text", "")
        if text:
            labels.append(
                (
                    screen_x,
                    screen_y,
                    _coord(element, "width"),
                    _coord(element, "height"),
                    element.get("style_text_align", "left"),
                    text,
                )
            )
        return

    if element.tag == "lv_obj" and element.get("style_bg_color") == "0x000000":
        bar_width = _coord(element, "width")
        bar_height = _coord(element, "height")
        if bar_width > 0 and bar_height > 0:
            bars.append((screen_x, screen_y, bar_width, bar_height))
        return

    child_origin_x = screen_x
    child_origin_y = screen_y
    flex_row = element.get("flex_flow") == "row"
    pad = _coord(element, "style_pad_all", 0)
    if pad == 0 and element.get("style_pad_all") is None:
        pad = 1 if flex_row else 0
    cursor_x = pad

    for child in element:
        if flex_row and child.get("x") is None and child.get("y") is None:
            _collect_drawables(
                child,
                child_origin_x + cursor_x,
                child_origin_y + pad,
                labels,
                bars,
            )
            cursor_x += _coord(child, "width", 40)
        else:
            _collect_drawables(child, child_origin_x, child_origin_y, labels, bars)


def _resolve_preview_image(src: str, screen_path: Path | None) -> Path | None:
    path = Path(src)
    candidates: list[Path] = []
    if screen_path is not None:
        candidates.append((screen_path.parent / path).resolve())
    candidates.append((Path.cwd() / path).resolve())
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def preview_png(
    xml_text: str,
    output_path: Path,
    screen_path: Path | None = None,
    dither_override: str | None = None,
) -> None:
    root = ET.fromstring(xml_text)
    view = root.find("view")
    width = (
        int(view.get("width", str(PREVIEW_WIDTH)))
        if view is not None
        else PREVIEW_WIDTH
    )
    height = (
        int(view.get("height", str(PREVIEW_HEIGHT)))
        if view is not None
        else PREVIEW_HEIGHT
    )

    wasm_js = (
        Path(__file__).resolve().parents[1]
        / "build"
        / "lvgl_wasm"
        / "web"
        / "preview.js"
    )
    selected_algorithms = {
        dither_override or element.get("dither", "none")
        for element in root.iter("lv_image")
    }
    if (
        wasm_js.exists()
        and dither_override is None
        and selected_algorithms == {"none"}
    ):
        _preview_with_wasm(xml_text, output_path, width, height, screen_path)
        return

    Image, ImageDraw, ImageFont = _load_pillow()
    labels: list[tuple[int, int, int, int, str, str]] = []
    bars: list[tuple[int, int, int, int]] = []
    if view is not None:
        _collect_drawables(view, 0, 0, labels, bars)
    else:
        _collect_drawables(root, 0, 0, labels, bars)

    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    for element in root.iter("lv_image"):
        src = element.get("src")
        if not src or _is_hidden(element):
            continue
        resolved = _resolve_preview_image(src, screen_path)
        if resolved is None:
            continue
        req_w = _coord(element, "width") or None
        req_h = _coord(element, "height") or None
        if req_w == 0:
            req_w = None
        if req_h == 0:
            req_h = None
        sprite = preview_rgba_image(
            resolved,
            req_w,
            req_h,
            dither_override or element.get("dither", "none"),
        )
        x = _coord(element, "x")
        y = _coord(element, "y")
        image.alpha_composite(sprite, (x, y))
    # No dither: anti-aliased SVG fringes must hard-threshold, not speckled.
    mono = image.convert("1", dither=Image.Dither.NONE)
    draw = ImageDraw.Draw(mono)
    font = ImageFont.load_default()
    for x, y, label_width, _, alignment, text in labels:
        text_bounds = draw.textbbox((0, 0), text, font=font)
        text_width = text_bounds[2] - text_bounds[0]
        if label_width > 0 and alignment == "center":
            x += (label_width - text_width) // 2
        elif label_width > 0 and alignment == "right":
            x += label_width - text_width
        draw.text((x, y), text, fill=0, font=font)
    for x, y, bar_width, bar_height in bars:
        draw.rectangle(
            (
                x,
                y,
                min(width - 1, x + bar_width - 1),
                min(height - 1, y + bar_height - 1),
            ),
            fill=0,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mono.save(output_path, format="PNG")


def _preview_with_wasm(
    xml_text: str,
    output_path: Path,
    width: int,
    height: int,
    screen_path: Path | None,
) -> None:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("node is required for WebAssembly LVGL preview")
    script = Path(__file__).parent / "lvgl_wasm" / "render_cli.js"
    if not script.exists():
        raise RuntimeError(f"missing wasm helper script: {script}")
    root = ET.fromstring(xml_text)
    images = [element for element in root.iter("lv_image") if not _is_hidden(element)]
    parents = {child: parent for parent in root.iter() for child in parent}
    for element in images:
        parent = parents.get(element)
        if parent is not None:
            parent.remove(element)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as handle:
        handle.write(ET.tostring(root, encoding="unicode", short_empty_elements=False))
        xml_path = handle.name
    with tempfile.NamedTemporaryFile(suffix=".rgba", delete=False) as handle:
        rendered_path = Path(handle.name)
    try:
        result = subprocess.run(
            [node, str(script), xml_path, str(rendered_path), str(width), str(height)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "wasm preview failed")
        rgba = rendered_path.read_bytes()
        if len(rgba) != width * height * 4:
            raise RuntimeError("LVGL preview returned an invalid framebuffer size")
        Image, _, _ = _load_pillow()
        background = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        for element in images:
            source = element.get("src")
            if not source:
                continue
            resolved = _resolve_preview_image(source, screen_path)
            if resolved is None:
                continue
            req_w = _coord(element, "width") or None
            req_h = _coord(element, "height") or None
            sprite = preview_rgba_image(resolved, req_w, req_h)
            background.alpha_composite(
                sprite, (_coord(element, "x"), _coord(element, "y"))
            )
        foreground = Image.frombytes(
            "RGBA", (width, height), rgba, "raw", "BGRA"
        ).convert("L")
        foreground_mask = foreground.point(lambda pixel: 255 if pixel < 128 else 0)
        background.paste((0, 0, 0, 255), (0, 0, width, height), foreground_mask)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        background.convert("1", dither=Image.Dither.NONE).save(
            output_path, format="PNG"
        )
    finally:
        Path(xml_path).unlink(missing_ok=True)
        rendered_path.unlink(missing_ok=True)

"""Generate LVGL screen C/H sources from validated component XML."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

if __package__:
    from tools.nice_view_xml_assets import (
        DITHER_ALGORITHMS,
        load_i1_gif_frames,
        load_i1_image,
        load_i2_gif_frames,
        load_i2_image,
    )
else:
    from nice_view_xml_assets import (
        DITHER_ALGORITHMS,
        load_i1_gif_frames,
        load_i1_image,
        load_i2_gif_frames,
        load_i2_image,
    )

MAX_DYNAMIC_BINDINGS = 22
MAX_VISIBLE_ASSETS = 16
MAX_ANIMATION_FRAMES = 64
MAX_ANIMATION_BYTES = 32768
ROLES = {"central": 1, "peripheral": 2}
RENDERERS = {
    "text": "ZMK_NVP_SVG_RENDER_TEXT",
    "percent": "ZMK_NVP_SVG_RENDER_PERCENT",
    "bar": "ZMK_NVP_SVG_RENDER_BAR",
    "ring": "ZMK_NVP_SVG_RENDER_RING",
    "visible": "ZMK_NVP_SVG_RENDER_VISIBLE",
}
IF_INVERTED = "#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND"
ELSE_DIRECTIVE = "#else"
ENDIF_DIRECTIVE = "#endif"
I1_COLOR_PALETTE = [
    IF_INVERTED,
    "    0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff,",
    ELSE_DIRECTIVE,
    "    0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0xff,",
    ENDIF_DIRECTIVE,
]
I2_COLOR_PALETTE = [
    IF_INVERTED,
    "    0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,",
    "    0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00, 0x00,",
    ELSE_DIRECTIVE,
    "    0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0xff,",
    "    0xff, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00,",
    ENDIF_DIRECTIVE,
]


@dataclass
class StaticLabel:
    text: str
    x: int
    y: int
    font_size: int = 10
    font_family: str = ""
    width: int = 0
    height: int = 0
    text_align: str = ""


@dataclass
class StaticImage:
    path: Path
    x: int
    y: int
    width: int
    height: int
    bitmap: bytes
    animation_index: int = 255
    format_i2: bool = False


@dataclass
class VisibleAsset:
    width: int
    height: int
    bitmap: bytes
    animation_index: int = 255


@dataclass
class AnimationFrame:
    bitmap: bytes
    duration_ms: int


@dataclass
class Animation:
    width: int
    height: int
    frames: list[AnimationFrame]
    repeat_count: int
    format_i2: bool


@dataclass
class BindingSpec:
    field_id: str
    renderer: str
    roles: int
    x: int
    y: int
    width: int
    height: int
    ring_radius: int
    ring_width: int
    ring_rounded: int
    font_size: int
    format_name: str
    prefix: str
    when: str
    match_bit: int
    visible_child_text: str
    anchor: str = "start"
    asset_index: int = 255


@dataclass
class ScreenModel:
    width: int
    height: int
    static_labels: list[StaticLabel] = field(default_factory=list)
    static_images: list[StaticImage] = field(default_factory=list)
    bindings: list[BindingSpec] = field(default_factory=list)
    visible_assets: list[VisibleAsset] = field(default_factory=list)
    animations: list[Animation] = field(default_factory=list)


def _int_attr(element: ET.Element, name: str, default: int = 0) -> int:
    value = element.get(name)
    if value is None or not re.fullmatch(r"-?\d+", value):
        return default
    return int(value)


def _static_label_font(font_size: int, font_family: str = "") -> str:
    if font_size >= 16:
        return "&lv_font_montserrat_20"
    if font_size > 8:
        return "&lv_font_montserrat_12"
    if font_family == "monospace":
        return "&lv_font_unscii_8"
    return "&lv_font_montserrat_8"


def _static_label_lines(label: StaticLabel) -> list[str]:
    font = _static_label_font(label.font_size, label.font_family)
    lines = [
        "    {",
        "        lv_obj_t *label = lv_label_create(screen);",
        f"        lv_label_set_text(label, {_c_string(label.text)});",
        f"        lv_obj_set_style_text_font(label, {font}, LV_PART_MAIN);",
        f"        lv_obj_set_pos(label, {label.x}, {label.y});",
    ]
    if label.width > 0 and label.height > 0:
        lines.append(f"        lv_obj_set_size(label, {label.width}, {label.height});")
    text_align = {
        "left": "LV_TEXT_ALIGN_LEFT",
        "center": "LV_TEXT_ALIGN_CENTER",
        "right": "LV_TEXT_ALIGN_RIGHT",
    }.get(label.text_align)
    if text_align is not None:
        lines.append(
            f"        lv_obj_set_style_text_align(label, {text_align}, LV_PART_MAIN);"
        )
    lines.extend(
        [
            "        lv_obj_set_style_text_color(label, xml_foreground(), LV_PART_MAIN);",
            "    }",
        ]
    )
    return lines


def _optional_positive_int(element: ET.Element, name: str) -> int | None:
    value = element.get(name)
    if value is None or not re.fullmatch(r"\d+", value):
        return None
    number = int(value)
    return number if number > 0 else None


def _binding_roles(element: ET.Element) -> int:
    role = element.get("role")
    if role is None:
        return ROLES["central"] | ROLES["peripheral"]
    if role == "central":
        return ROLES["central"]
    if role == "peripheral":
        return ROLES["peripheral"]
    return ROLES["central"] | ROLES["peripheral"]


def _when_string(element: ET.Element) -> str:
    test = element.get("test")
    if test == "equals":
        return element.get("value", "")
    if test == "bit_set":
        return "set"
    if test == "bit_clear":
        return "clear"
    return ""


def _resolve_image_path(src: str, screen_path: Path | None) -> Path:
    path = Path(src)
    if path.is_absolute() and path.exists():
        return path
    candidates: list[Path] = []
    if screen_path is not None:
        candidates.append((screen_path.parent / path).resolve())
    candidates.append((Path.cwd() / path).resolve())
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise ValueError(f"lv_image src not found: {src}")


def _load_image(
    path: Path,
    width: int | None,
    height: int | None,
    model: ScreenModel,
    format_i2: bool,
    dither: str,
) -> tuple[int, int, bytes, int]:
    if dither not in DITHER_ALGORITHMS:
        raise ValueError(
            f"unknown dithering algorithm '{dither}'; choose from "
            f"{', '.join(DITHER_ALGORITHMS)}"
        )
    if path.suffix.lower() != ".gif":
        loader = load_i2_image if format_i2 else load_i1_image
        image_width, image_height, bitmap = loader(path, width, height, dither)
        return image_width, image_height, bitmap, 255

    loader = load_i2_gif_frames if format_i2 else load_i1_gif_frames
    image_width, image_height, raw_frames, repeat_count = loader(
        path, width, height, dither
    )
    if len(raw_frames) == 1:
        return image_width, image_height, raw_frames[0][0], 255
    if len(raw_frames) > MAX_ANIMATION_FRAMES:
        raise ValueError(
            f"GIF has {len(raw_frames)} frames; budget is {MAX_ANIMATION_FRAMES}"
        )
    total_bytes = sum(len(bitmap) for bitmap, _ in raw_frames)
    if total_bytes > MAX_ANIMATION_BYTES:
        raise ValueError(
            f"GIF embeds {total_bytes} bytes of monochrome frames; "
            f"budget is {MAX_ANIMATION_BYTES}"
        )
    if len(model.animations) >= 255:
        raise ValueError("screen has too many animated images; budget is 255")

    animation_index = len(model.animations)
    model.animations.append(
        Animation(
            width=image_width,
            height=image_height,
            frames=[
                AnimationFrame(bitmap=bitmap, duration_ms=duration)
                for bitmap, duration in raw_frames
            ],
            repeat_count=repeat_count,
            format_i2=format_i2,
        )
    )
    return image_width, image_height, raw_frames[0][0], animation_index


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _is_under_when(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    current = parents.get(element)
    while current is not None:
        if current.tag == "zmk_status_when":
            return True
        current = parents.get(current)
    return False


def collect_bindings(
    root: ET.Element,
    screen_path: Path | None = None,
    dither_override: str | None = None,
) -> ScreenModel:
    views = root.findall("view")
    if len(views) != 1:
        raise ValueError("component must contain exactly one direct <view>")
    view = views[0]
    width = _int_attr(view, "width")
    height = _int_attr(view, "height")
    if width <= 0 or height <= 0:
        raise ValueError("<view> needs positive width and height")

    model = ScreenModel(width=width, height=height)
    parents = _parent_map(root)

    for element in root.iter():
        if element.tag == "lv_image":
            if _is_under_when(element, parents):
                continue
            src = element.get("src")
            if not src:
                raise ValueError("<lv_image> needs a src attribute")
            image_path = _resolve_image_path(src, screen_path)
            req_w = _optional_positive_int(element, "width")
            req_h = _optional_positive_int(element, "height")
            img_w, img_h, bitmap, animation_index = _load_image(
                image_path,
                req_w,
                req_h,
                model,
                format_i2=False,
                dither=dither_override or element.get("dither", "none"),
            )
            model.static_images.append(
                StaticImage(
                    path=image_path,
                    x=_int_attr(element, "x"),
                    y=_int_attr(element, "y"),
                    width=img_w,
                    height=img_h,
                    bitmap=bitmap,
                    animation_index=animation_index,
                )
            )
        elif element.tag == "lv_label" and element.get("field") is None:
            if _is_under_when(element, parents):
                continue
            text = element.get("text")
            if text:
                model.static_labels.append(
                    StaticLabel(
                        text=text,
                        x=_int_attr(element, "x"),
                        y=_int_attr(element, "y"),
                        font_size=_int_attr(element, "font_size", 10),
                        font_family=element.get("font_family", ""),
                        width=_int_attr(element, "width"),
                        height=_int_attr(element, "height"),
                        text_align=element.get("style_text_align", ""),
                    )
                )
        elif element.tag == "zmk_status_text":
            fmt = element.get("format", "text")
            renderer = "percent" if fmt == "percent" else "text"
            format_name = {
                "percent": "percent",
                "output-label": "output-label",
                "profile-number": "profile-number",
                "text": "value",
            }.get(fmt, "value")
            model.bindings.append(
                BindingSpec(
                    field_id=element.get("field", ""),
                    renderer=renderer,
                    roles=_binding_roles(element),
                    x=_int_attr(element, "x"),
                    y=_int_attr(element, "y"),
                    width=_int_attr(element, "width"),
                    height=_int_attr(element, "height"),
                    ring_radius=0,
                    ring_width=0,
                    ring_rounded=0,
                    font_size=_int_attr(
                        element, "font_size", 11 if renderer == "percent" else 10
                    ),
                    format_name=format_name,
                    prefix="",
                    when="",
                    match_bit=0,
                    visible_child_text="",
                    anchor=element.get("anchor", "start"),
                )
            )
        elif element.tag == "zmk_status_bar":
            model.bindings.append(
                BindingSpec(
                    field_id=element.get("field", ""),
                    renderer="bar",
                    roles=_binding_roles(element),
                    x=_int_attr(element, "x"),
                    y=_int_attr(element, "y"),
                    width=_int_attr(element, "width", 1),
                    height=_int_attr(element, "height", 4),
                    ring_radius=0,
                    ring_width=0,
                    ring_rounded=0,
                    font_size=0,
                    format_name="value",
                    prefix="",
                    when="",
                    match_bit=0,
                    visible_child_text="",
                )
            )
        elif element.tag == "zmk_status_arc":
            radius = _int_attr(element, "radius", 10)
            model.bindings.append(
                BindingSpec(
                    field_id=element.get("field", ""),
                    renderer="ring",
                    roles=_binding_roles(element),
                    x=_int_attr(element, "x"),
                    y=_int_attr(element, "y"),
                    width=0,
                    height=0,
                    ring_radius=radius,
                    ring_width=_int_attr(element, "ring_width", 2),
                    ring_rounded=1,
                    font_size=0,
                    format_name="value",
                    prefix="",
                    when="",
                    match_bit=0,
                    visible_child_text="",
                )
            )
        elif element.tag == "zmk_status_when":
            image_child = next(
                (node for node in element if node.tag == "lv_image"), None
            )
            label_child = next(
                (node for node in element if node.tag == "lv_label"), None
            )
            asset_index = 255
            child_text = ""
            if image_child is not None:
                src = image_child.get("src")
                if not src:
                    raise ValueError(
                        "<zmk_status_when> <lv_image> needs a src attribute"
                    )
                image_path = _resolve_image_path(src, screen_path)
                req_w = _optional_positive_int(image_child, "width")
                req_h = _optional_positive_int(image_child, "height")
                img_w, img_h, bitmap, animation_index = _load_image(
                    image_path,
                    req_w,
                    req_h,
                    model,
                    format_i2=True,
                    dither=dither_override or image_child.get("dither", "none"),
                )
                if len(model.visible_assets) >= MAX_VISIBLE_ASSETS:
                    raise ValueError(
                        f"screen has too many visible image assets; "
                        f"budget is {MAX_VISIBLE_ASSETS}"
                    )
                asset_index = len(model.visible_assets)
                model.visible_assets.append(
                    VisibleAsset(
                        width=img_w,
                        height=img_h,
                        bitmap=bitmap,
                        animation_index=animation_index,
                    )
                )
                child = image_child
            elif label_child is not None:
                child_text = label_child.get("text", "")
                child = label_child
            else:
                child = element
            model.bindings.append(
                BindingSpec(
                    field_id=element.get("field", ""),
                    renderer="visible",
                    roles=_binding_roles(element),
                    x=_int_attr(child, "x"),
                    y=_int_attr(child, "y"),
                    width=_int_attr(child, "width", 24),
                    height=_int_attr(child, "height", 12),
                    ring_radius=0,
                    ring_width=0,
                    ring_rounded=0,
                    font_size=_int_attr(child, "font_size", 10),
                    format_name="value",
                    prefix=child_text,
                    when=_when_string(element),
                    match_bit=_int_attr(element, "bit"),
                    visible_child_text=child_text,
                    asset_index=asset_index,
                )
            )

    if len(model.bindings) > MAX_DYNAMIC_BINDINGS:
        raise ValueError(
            f"screen has {len(model.bindings)} dynamic bindings; "
            f"budget is {MAX_DYNAMIC_BINDINGS}"
        )
    return model


def _c_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _emit_i1_image_c(
    lines: list[str], symbol: str, image: StaticImage, format_i2: bool = False
) -> None:
    stride = (image.width + 3) // 4 if format_i2 else (image.width + 7) // 8
    lines.extend(
        [
            "static const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST uint8_t",
            f"    {symbol}_data[] = {{",
        ]
    )
    lines.extend(I2_COLOR_PALETTE if format_i2 else I1_COLOR_PALETTE)
    for offset in range(0, len(image.bitmap), 16):
        chunk = image.bitmap[offset : offset + 16]
        lines.append("    " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    lines.extend(
        [
            "};",
            "",
            f"static const lv_image_dsc_t {symbol} = {{",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            f"        .cf = {'LV_COLOR_FORMAT_I2' if format_i2 else 'LV_COLOR_FORMAT_I1'},",
            f"        .w = {image.width},",
            f"        .h = {image.height},",
            f"        .stride = {stride},",
            "    },",
            f"    .data_size = sizeof({symbol}_data),",
            f"    .data = {symbol}_data,",
            "};",
            "",
        ]
    )


def _emit_i2_visible_c(lines: list[str], assets: list[VisibleAsset]) -> None:
    for index, asset in enumerate(assets):
        if asset.animation_index != 255:
            continue
        stride = (asset.width + 3) // 4
        lines.extend(
            [
                "static const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST uint8_t",
                f"    zmk_nvp_svg_visible_{index}_data[] = {{",
                *I2_COLOR_PALETTE,
            ]
        )
        for offset in range(0, len(asset.bitmap), 16):
            chunk = asset.bitmap[offset : offset + 16]
            lines.append("    " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
        lines.extend(
            [
                "};",
                f"static const lv_image_dsc_t zmk_nvp_svg_visible_{index} = {{",
                "    .header = {",
                "        .magic = LV_IMAGE_HEADER_MAGIC,",
                "        .cf = LV_COLOR_FORMAT_I2,",
                f"        .w = {asset.width},",
                f"        .h = {asset.height},",
                f"        .stride = {stride},",
                "    },",
                f"    .data_size = sizeof(zmk_nvp_svg_visible_{index}_data),",
                f"    .data = zmk_nvp_svg_visible_{index}_data,",
                "};",
                "",
            ]
        )
    lines.append("const lv_image_dsc_t *const zmk_nvp_svg_visible_assets[] = {")
    if assets:
        for index, asset in enumerate(assets):
            if asset.animation_index == 255:
                lines.append(f"    &zmk_nvp_svg_visible_{index},")
            else:
                lines.append(
                    f"    &zmk_nvp_svg_animation_{asset.animation_index}_frame_0,"
                )
    else:
        lines.append("    0,")
    lines.extend(["};", ""])
    lines.append("const uint8_t zmk_nvp_svg_visible_animation_indices[] = {")
    if assets:
        lines.extend(f"    {asset.animation_index}," for asset in assets)
    else:
        lines.append("    255,")
    lines.extend(["};", ""])


def _emit_animation_tables(lines: list[str], animations: list[Animation]) -> None:
    for index, animation in enumerate(animations):
        lines.append(
            f"static const lv_image_dsc_t *const zmk_nvp_svg_animation_{index}_frames[] = {{"
        )
        lines.extend(
            f"    &zmk_nvp_svg_animation_{index}_frame_{frame_index},"
            for frame_index in range(len(animation.frames))
        )
        lines.extend(["};", ""])
        lines.append(f"static const uint32_t zmk_nvp_svg_animation_{index}_durations[] = {{")
        lines.extend(f"    {frame.duration_ms}U," for frame in animation.frames)
        lines.extend(["};", ""])

    lines.append("const struct zmk_nvp_svg_animation zmk_nvp_svg_animations[] = {")
    if animations:
        for index, animation in enumerate(animations):
            lines.append(
                "    { "
                f"zmk_nvp_svg_animation_{index}_frames, "
                f"zmk_nvp_svg_animation_{index}_durations, "
                f"{len(animation.frames)}, {animation.repeat_count}U "
                "},"
            )
    else:
        lines.append("    { 0 },")
    lines.extend(["};", ""])


def _emit_image_descriptors(lines: list[str], model: ScreenModel) -> None:
    for animation_index, animation in enumerate(model.animations):
        for frame_index, frame in enumerate(animation.frames):
            image = StaticImage(
                path=Path(),
                x=0,
                y=0,
                width=animation.width,
                height=animation.height,
                bitmap=frame.bitmap,
            )
            _emit_i1_image_c(
                lines,
                f"zmk_nvp_svg_animation_{animation_index}_frame_{frame_index}",
                image,
                format_i2=animation.format_i2,
            )

    for index, image in enumerate(model.static_images):
        if image.animation_index != 255:
            continue
        symbol = (
            "zmk_nvp_svg_background" if index == 0 else f"zmk_nvp_xml_static_{index}"
        )
        _emit_i1_image_c(lines, symbol, image)

    _emit_i2_visible_c(lines, model.visible_assets)
    _emit_animation_tables(lines, model.animations)


def _emit_static_image_layout(lines: list[str], images: list[StaticImage]) -> None:
    for index, image in enumerate(images):
        if image.animation_index != 255:
            lines.extend(
                [
                    "    zmk_nvp_xml_animation_create(",
                    f"        screen, &zmk_nvp_svg_animations[{image.animation_index}],",
                    f"        {image.x}, {image.y}, false);",
                ]
            )
            continue
        symbol = "zmk_nvp_svg_background" if index == 0 else f"zmk_nvp_xml_static_{index}"
        lines.extend(
            [
                "    {",
                "        lv_obj_t *image = lv_image_create(screen);",
                f"        lv_image_set_src(image, &{symbol});",
                f"        lv_obj_set_pos(image, {image.x}, {image.y});",
                "    }",
            ]
        )


def generate_sources(
    xml_text: str,
    screen_path: Path | None = None,
    dither_override: str | None = None,
) -> tuple[str, str]:
    root = ET.fromstring(xml_text)
    if root.tag != "component":
        raise ValueError("root element must be <component>")
    model = collect_bindings(root, screen_path, dither_override)
    has_background = 1 if model.static_images else 0

    header_lines = [
        "#pragma once",
        "#include <lvgl.h>",
        "#include <stdint.h>",
        "",
        "#ifndef LV_ATTRIBUTE_MEM_ALIGN",
        "#define LV_ATTRIBUTE_MEM_ALIGN",
        ENDIF_DIRECTIVE,
        "#ifndef LV_ATTRIBUTE_LARGE_CONST",
        "#define LV_ATTRIBUTE_LARGE_CONST",
        ENDIF_DIRECTIVE,
        "",
        f"#define ZMK_NVP_SVG_WIDTH {model.width}",
        f"#define ZMK_NVP_SVG_HEIGHT {model.height}",
        f"#define ZMK_NVP_SVG_BINDING_COUNT {len(model.bindings)}",
        f"#define ZMK_NVP_SVG_VISIBLE_ASSET_COUNT {len(model.visible_assets)}",
        f"#define ZMK_NVP_SVG_ANIMATION_COUNT {len(model.animations)}",
        f"#define ZMK_NVP_XML_HAS_BACKGROUND {has_background}",
        "",
        "enum zmk_nvp_svg_renderer {",
        "    ZMK_NVP_SVG_RENDER_BAR = 0,",
        "    ZMK_NVP_SVG_RENDER_PERCENT = 1,",
        "    ZMK_NVP_SVG_RENDER_RING = 2,",
        "    ZMK_NVP_SVG_RENDER_TEXT = 3,",
        "    ZMK_NVP_SVG_RENDER_VISIBLE = 4,",
        "};",
        "",
        "struct zmk_nvp_svg_binding {",
        "    const char *field_id;",
        "    uint8_t renderer;",
        "    uint8_t roles;",
        "    uint8_t asset_index;",
        "    int16_t x, y, width, height;",
        "    int16_t ring_radius;",
        "    uint8_t ring_width;",
        "    uint8_t ring_rounded;",
        "    uint8_t font_size;",
        "    uint8_t color;",
        "    const char *font_family;",
        "    const char *anchor;",
        "    const char *format;",
        "    const char *prefix;",
        "    const char *suffix;",
        "    const char *when;",
        "    uint8_t match_bit;",
        "};",
        "",
        "struct zmk_nvp_svg_animation {",
        "    const lv_image_dsc_t *const *frames;",
        "    const uint32_t *durations_ms;",
        "    uint16_t frame_count;",
        "    uint32_t repeat_count;",
        "};",
        "",
        (
            f"extern const struct zmk_nvp_svg_binding "
            f"zmk_nvp_svg_bindings[{len(model.bindings) or 1}];"
        ),
        "extern const lv_image_dsc_t *const zmk_nvp_svg_visible_assets[];",
        "extern const uint8_t zmk_nvp_svg_visible_animation_indices[];",
        (
            f"extern const struct zmk_nvp_svg_animation "
            f"zmk_nvp_svg_animations[{len(model.animations) or 1}];"
        ),
        "lv_obj_t *zmk_nvp_xml_animation_create(",
        "    lv_obj_t *parent, const struct zmk_nvp_svg_animation *animation,",
        "    int16_t x, int16_t y, bool initially_paused);",
        "void zmk_nvp_xml_animation_attach(",
        "    lv_obj_t *image, const struct zmk_nvp_svg_animation *animation,",
        "    bool initially_paused);",
        "void zmk_nvp_xml_animation_set_paused(lv_obj_t *image, bool paused);",
        "void zmk_nvp_xml_layout_create(lv_obj_t *screen);",
        "",
    ]

    binding_rows = []
    for binding in model.bindings:
        binding_rows.append(
            "    { "
            + ", ".join(
                [
                    _c_string(binding.field_id),
                    RENDERERS[binding.renderer],
                    str(binding.roles),
                    str(binding.asset_index),
                    str(binding.x),
                    str(binding.y),
                    str(binding.width),
                    str(binding.height),
                    str(binding.ring_radius),
                    str(binding.ring_width),
                    str(binding.ring_rounded),
                    str(binding.font_size),
                    "0",
                    _c_string("monospace"),
                    _c_string(binding.anchor),
                    _c_string(binding.format_name),
                    _c_string(binding.prefix),
                    _c_string(""),
                    _c_string(binding.when),
                    str(binding.match_bit),
                ]
            )
            + " },"
        )
    if not binding_rows:
        binding_rows.append("    { 0 },")

    c_lines = [
        '#include "status_screen_gen.h"',
        "#include <stdbool.h>",
        "#include <stdio.h>",
        "#include <string.h>",
        "",
        "#include <lvgl.h>",
        "",
    ]
    _emit_image_descriptors(c_lines, model)

    c_lines.extend(
        [
            "const struct zmk_nvp_svg_binding zmk_nvp_svg_bindings[] = {",
            *binding_rows,
            "};",
            "",
            "static lv_color_t xml_foreground(void)",
            "{",
            "#if CONFIG_NICE_VIEW_WIDGET_INVERTED && !CONFIG_ZMK_SVG_WHITE_BACKGROUND",
            "    return lv_color_white();",
            "#else",
            "    return lv_color_black();",
            "#endif",
            "}",
            "",
            "void zmk_nvp_xml_layout_create(lv_obj_t *screen)",
            "{",
            "    if (screen == NULL) {",
            "        return;",
            "    }",
            "    lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);",
        ]
    )

    _emit_static_image_layout(c_lines, model.static_images)

    for label in model.static_labels:
        c_lines.extend(_static_label_lines(label))

    c_lines.extend(["}", ""])

    return "\n".join(header_lines).rstrip() + "\n", "\n".join(c_lines).rstrip() + "\n"


def write_generated(
    screen_path: Path,
    output_dir: Path,
    xml_text: str | None = None,
    dither_override: str | None = None,
) -> tuple[Path, Path]:
    if xml_text is None:
        xml_text = screen_path.read_text()
    header, source = generate_sources(xml_text, screen_path, dither_override)
    output_dir.mkdir(parents=True, exist_ok=True)
    header_path = output_dir / "status_screen_gen.h"
    source_path = output_dir / "status_screen_gen.c"
    header_path.write_text(header)
    source_path.write_text(source)
    return header_path, source_path

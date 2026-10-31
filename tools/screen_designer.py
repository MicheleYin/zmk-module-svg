"""Compose editable screen modules into the existing LVGL XML pipeline."""

from __future__ import annotations

import json
import math
import os
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

if __package__:
    from tools.nice_view_xml_assets import DITHER_ALGORITHMS, rasterize_svg_file
else:
    from nice_view_xml_assets import DITHER_ALGORITHMS, rasterize_svg_file

ROOT = Path(__file__).resolve().parents[1]
PROFILE_SIZES = {"nice-view": (160, 68), "oled": (128, 32)}
HALVES = ("left", "right")
INSTANCE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
ARTWORK_SUFFIXES = {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp"}
SCREEN_NAMES = {
    ("nice-view", "left"): "nice-view-left.xml",
    ("nice-view", "right"): "nice-view-right.xml",
    ("oled", "left"): "oled-left.xml",
    ("oled", "right"): "oled-right.xml",
}


def load_visual_modules(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    catalog_path = root / "tools" / "visual_modules.json"
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("modules"), list):
        raise ValueError("invalid visual module catalog")

    modules = {}
    for module in data["modules"]:
        module_id = module.get("id")
        if not isinstance(module_id, str) or module_id in modules:
            raise ValueError("visual module IDs must be unique strings")
        if not (root / module["source"]).is_file():
            raise ValueError(f"visual module source is missing: {module_id}")
        if not isinstance(module.get("defaults"), dict) or not isinstance(
            module.get("bounds"), dict
        ):
            raise ValueError(f"visual module needs defaults and bounds: {module_id}")
        modules[module_id] = module
    return modules


def available_lucide_icons(root: Path = ROOT) -> list[dict[str, str]]:
    asset_dir = root / "docs" / "ui" / "assets"
    return [
        {
            "name": "No icon" if path.name == "no-icon.svg" else path.stem,
            "src": f"../assets/{path.relative_to(asset_dir).as_posix()}",
        }
        for path in sorted(asset_dir.rglob("*.svg"))
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", path.stem)
    ]


def empty_screen_design() -> dict[str, Any]:
    return {"items": []}


def _number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _validate_box(
    instance: dict[str, Any], size: tuple[int, int], label: str
) -> dict[str, int]:
    width, height = size
    box = {}
    for key in ("x", "y", "width", "height"):
        value = round(_number(instance.get(key), f"{label} {key}"))
        box[key] = value
    if box["x"] < 0 or box["y"] < 0 or box["width"] < 1 or box["height"] < 1:
        raise ValueError(f"{label} must have positive size and non-negative position")
    if box["x"] + box["width"] > width or box["y"] + box["height"] > height:
        raise ValueError(f"{label} must fit within the {width}x{height} display")
    return box


def validate_screen_design(
    profile: str,
    side: str,
    design: dict[str, Any],
    input_dir: Path,
    modules: dict[str, dict[str, Any]] | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    if profile not in PROFILE_SIZES:
        raise ValueError(f"unknown display profile: {profile}")
    if side not in HALVES:
        raise ValueError(f"unknown display half: {side}")
    if not isinstance(design, dict):
        raise ValueError("screen design must be an object")

    modules = modules or load_visual_modules()
    size = PROFILE_SIZES[profile]
    if "items" in design:
        items = design["items"]
        if not isinstance(items, list):
            raise ValueError("screen design needs an item list")
    else:
        items = []
        background = design.get("background")
        if background is not None:
            items.append(
                {
                    "id": "background",
                    "kind": "image",
                    "x": 0,
                    "y": 0,
                    "width": size[0],
                    "height": size[1],
                    "properties": background,
                }
            )
        widgets = design.get("widgets", [])
        if not isinstance(widgets, list):
            raise ValueError("screen design needs a widget list")
        items.extend({"kind": "module", **widget} for widget in widgets)

    clean_items = []
    seen_ids = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"item {index + 1} must be an object")
        item_id = item.get("id")
        kind = item.get("kind", "module")
        module_id = item.get("module")
        if kind == "image":
            module_id = "background-image"
        label = f"item {index + 1}"
        if isinstance(item_id, str):
            label = f"item {item_id}"
        if not isinstance(item_id, str) or not INSTANCE_ID.fullmatch(item_id):
            raise ValueError(f"{label} has an invalid instance ID")
        if item_id in seen_ids:
            raise ValueError(f"duplicate item instance ID: {item_id}")
        seen_ids.add(item_id)
        module = modules.get(module_id)
        if module is None:
            raise ValueError(f"unknown widget module: {module_id}")
        box = _validate_box(item, size, label)
        properties = item.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError(f"{label} properties must be an object")

        if kind == "image":
            image_name = properties.get("image")
            if not isinstance(image_name, str) or Path(image_name).name != image_name:
                raise ValueError("choose an image from the artwork library")
            if Path(image_name).suffix.lower() not in ARTWORK_SUFFIXES:
                raise ValueError(f"unsupported image type: {image_name}")
            if not (input_dir / image_name).is_file():
                raise ValueError(f"image not found: {image_name}")
            fit = properties.get("fit", "cover")
            dither = properties.get("dither", "none")
            if fit not in {"cover", "contain"}:
                raise ValueError("image fit must be cover or contain")
            if dither not in DITHER_ALGORITHMS:
                raise ValueError(f"unknown dithering mode: {dither}")
            rotation = properties.get("rotation", 0)
            if rotation not in {0, 90, 180, 270}:
                raise ValueError("image rotation must be 0, 90, 180, or 270")
            clean_properties = {
                "image": image_name,
                "fit": fit,
                "focal_x": min(1, max(0, _number(properties.get("focal_x", 0.5), "focal x"))),
                "focal_y": min(1, max(0, _number(properties.get("focal_y", 0.5), "focal y"))),
                "rotation": rotation,
                "dither": dither,
            }
        elif kind == "module":
            if module_id == "background-image":
                raise ValueError("image modules must use image items")
            unknown = set(properties) - set(module.get("controls", []))
            if unknown:
                raise ValueError(
                    f"item {item_id} has unsupported properties: "
                    + ", ".join(sorted(unknown))
                )
            clean_properties = {**module["defaults"], **properties}
            icon_properties = tuple(
                property_name
                for property_name in module.get("controls", [])
                if property_name == "icon_src" or property_name.endswith("_icon_src")
            )
            if icon_properties:
                available_sources = {
                    icon["src"] for icon in available_lucide_icons(root)
                }
                for property_name in icon_properties:
                    icon_source = clean_properties.get(property_name)
                    if not isinstance(icon_source, str) or icon_source not in available_sources:
                        raise ValueError(
                            f"item {item_id} needs an imported Lucide icon for {property_name}"
                        )
            if "side" in module.get("controls", []) and clean_properties["side"] not in {
                "left",
                "right",
            }:
                raise ValueError(f"item {item_id} side must be left or right")
            if (
                "side" in module.get("controls", [])
                and "label" in module.get("defaults", {})
            ):
                clean_properties["label"] = clean_properties["side"][0].upper()
        else:
            raise ValueError(f"unknown item kind: {kind}")

        clean_items.append(
            {
                "id": item_id,
                "kind": kind,
                **({"module": module_id} if kind == "module" else {}),
                **box,
                "properties": clean_properties,
            }
        )

    return {"items": clean_items}


def _render_background(
    source: Path,
    destination: Path,
    size: tuple[int, int],
    settings: dict[str, Any],
) -> Path:
    if __package__:
        from tools.artwork_editor import fit_image
    else:
        from artwork_editor import fit_image

    destination.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    durations = []
    if source.suffix.lower() == ".svg":
        image_source = BytesIO(rasterize_svg_file(source))
    else:
        image_source = source
    with Image.open(image_source) as image:
        frame_count = getattr(image, "n_frames", 1)
        loop = int(image.info.get("loop", 0))
        for frame_index in range(frame_count):
            image.seek(frame_index)
            frame = ImageOps.exif_transpose(image.convert("RGBA"))
            frames.append(fit_image(frame, size, settings))
            durations.append(max(20, min(int(image.info.get("duration") or 100), 60000)))

    if len(frames) > 1:
        destination = destination.with_suffix(".gif")
        frames[0].save(
            destination,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=loop,
            disposal=2,
            optimize=True,
        )
    else:
        frames[0].save(destination, format="PNG", optimize=True)
    return destination


def _geometry_attributes(
    module: dict[str, Any], instance: dict[str, Any]
) -> dict[str, str]:
    bounds = module["bounds"]
    attributes = {
        "editor_id": instance["id"],
        "editor_module": module["id"],
        "editor_x": str(instance["x"]),
        "editor_y": str(instance["y"]),
        "editor_width": str(instance["width"]),
        "editor_height": str(instance["height"]),
    }
    for key in ("x", "y", "width", "height"):
        attributes[f"editor_base_{key}"] = str(bounds[key])
    return attributes


def write_design_screen(
    profile: str,
    side: str,
    design: dict[str, Any],
    destination: Path,
    input_dir: Path,
    asset_output_dir: Path,
    root: Path = ROOT,
) -> Path:
    modules = load_visual_modules(root)
    design = validate_screen_design(profile, side, design, input_dir, modules, root)
    width, height = PROFILE_SIZES[profile]
    component = ET.Element("component")
    view = ET.SubElement(
        component,
        "view",
        {
            "extends": "lv_obj",
            "width": str(width),
            "height": str(height),
            "style_bg_color": "0xffffff",
            "style_pad_all": "0",
            "scrollable": "false",
        },
    )

    instances = []
    for item in design["items"]:
        if item["kind"] == "image":
            properties = item["properties"]
            module = modules["background-image"]
            asset_path = _render_background(
                input_dir / properties["image"],
                asset_output_dir / f"image-{profile}-{side}-{item['id']}.png",
                (item["width"], item["height"]),
                {
                    "fit": properties["fit"],
                    "x": properties["focal_x"],
                    "y": properties["focal_y"],
                    "rotation": properties["rotation"],
                },
            )
            module_path = root / module["source"]
            params = {
                "image_src": Path(os.path.relpath(asset_path, module_path.parent)).as_posix(),
                "width": str(module["bounds"]["width"]),
                "height": str(module["bounds"]["height"]),
                "dither": properties["dither"],
            }
            attributes = {
                "editor_image": properties["image"],
                "editor_fit": properties["fit"],
                "editor_focal_x": str(properties["focal_x"]),
                "editor_focal_y": str(properties["focal_y"]),
                "editor_rotation": str(properties["rotation"]),
                "editor_kind": "image",
            }
            instances.append((module, item, params, attributes))
            continue

        module = modules[item["module"]]
        params = dict(item["properties"])
        instances.append((module, item, params, {}))

    for module, instance, params, metadata in instances:
        module_path = root / module["source"]
        source = Path(os.path.relpath(module_path, destination.parent)).as_posix()
        attributes = {"src": source, **_geometry_attributes(module, instance), **metadata}
        attributes.update({name: str(value) for name, value in params.items()})
        ET.SubElement(view, "zmk_include", attributes)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "<!-- Generated by the screen designer; edit with tools/artwork_editor.py. -->\n"
        + ET.tostring(component, encoding="unicode")
        + "\n",
        encoding="utf-8",
    )
    return destination


def load_design_screen(path: Path, root: Path = ROOT) -> dict[str, Any]:
    if not path.is_file():
        return empty_screen_design()
    modules = load_visual_modules(root)
    root = ET.parse(path).getroot()
    design = empty_screen_design()
    for index, include in enumerate(root.iter("zmk_include")):
        module_id = include.get("editor_module")
        if module_id not in modules:
            continue
        module = modules[module_id]
        box = {
            key: int(float(include.get(f"editor_{key}", module["bounds"][key])))
            for key in ("x", "y", "width", "height")
        }
        item_id = include.get("editor_id", f"item-{index + 1}")
        if module_id == "background-image" or include.get("editor_kind") == "image":
            design["items"].append(
                {
                    "id": item_id,
                    "kind": "image",
                    **box,
                    "properties": {
                        "image": include.get("editor_image", ""),
                        "fit": include.get("editor_fit", "cover"),
                        "focal_x": float(include.get("editor_focal_x", "0.5")),
                        "focal_y": float(include.get("editor_focal_y", "0.5")),
                        "rotation": int(include.get("editor_rotation", "0")),
                        "dither": include.get("dither", "none"),
                    },
                }
            )
            continue
        design["items"].append(
            {
                "id": item_id,
                "kind": "module",
                "module": module_id,
                **box,
                "properties": {
                    key: include.get(key, str(value))
                    for key, value in module["defaults"].items()
                    if key in module.get("controls", [])
                },
            }
        )
    return design


def design_path(profile: str, side: str, root: Path = ROOT) -> Path:
    if profile not in PROFILE_SIZES or side not in HALVES:
        raise ValueError("unknown profile or display half")
    return root / "docs" / "ui" / "screens" / "designer" / f"{profile}-{side}.xml"


def load_profile_design(profile: str, root: Path = ROOT) -> dict[str, Any]:
    if profile not in PROFILE_SIZES:
        raise ValueError(f"unknown display profile: {profile}")
    return {
        side: load_design_screen(design_path(profile, side, root), root)
        for side in HALVES
    }


def write_profile_preview(
    profile: str,
    halves: dict[str, Any],
    input_dir: Path,
    root: Path = ROOT,
) -> tuple[Path, Path]:
    preview_dir = root / "build" / "screen_designer_preview"
    asset_dir = preview_dir / "assets"
    paths = []
    for side in HALVES:
        path = preview_dir / f"{profile}-{side}.xml"
        write_design_screen(
            profile,
            side,
            halves.get(side, empty_screen_design()),
            path,
            input_dir,
            asset_dir,
            root,
        )
        paths.append(path)
    return paths[0], paths[1]


def save_profile_design(
    profile: str,
    halves: dict[str, Any],
    input_dir: Path,
    root: Path = ROOT,
) -> tuple[Path, Path]:
    asset_dir = root / "docs" / "ui" / "assets" / "designer"
    paths = []
    for side in HALVES:
        path = design_path(profile, side, root)
        write_design_screen(
            profile,
            side,
            halves.get(side, empty_screen_design()),
            path,
            input_dir,
            asset_dir,
            root,
        )
        paths.append(path)
    return paths[0], paths[1]


def export_profile_design(
    profile: str,
    halves: dict[str, Any],
    input_dir: Path,
    root: Path = ROOT,
) -> tuple[Path, Path]:
    from tools.nice_view_xml import generate

    save_profile_design(profile, halves, input_dir, root)
    output_paths = []
    for side in HALVES:
        screen_path = root / "docs" / "ui" / "screens" / SCREEN_NAMES[(profile, side)]
        write_design_screen(
            profile,
            side,
            halves.get(side, empty_screen_design()),
            screen_path,
            input_dir,
            root / "docs" / "ui" / "assets" / "designer",
            root,
        )
        theme = f"{profile.replace('-', '_')}_{side}"
        generate(screen_path, root / "src" / "generated_xml" / theme)
        output_paths.append(screen_path)
    return output_paths[0], output_paths[1]
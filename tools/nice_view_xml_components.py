"""Expand reusable widget fragments in LVGL XML screens."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

PARAMETER = re.compile(r"\{\{([A-Za-z_]\w*)\}\}")
EDITOR_ATTRIBUTES = {
    "editor_id",
    "editor_x",
    "editor_y",
    "editor_width",
    "editor_height",
    "editor_base_x",
    "editor_base_y",
    "editor_base_width",
    "editor_base_height",
}


def _substitute(root: ET.Element, parameters: dict[str, str], source: Path) -> None:
    used: set[str] = set()

    def replace(value: str | None) -> str | None:
        if value is None:
            return None

        def replacement(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in parameters:
                raise ValueError(f"{source}: missing widget parameter '{name}'")
            used.add(name)
            return parameters[name]

        return PARAMETER.sub(replacement, value)

    for element in root.iter():
        element.attrib.update(
            {name: replace(value) or "" for name, value in element.attrib.items()}
        )
        element.text = replace(element.text)

    unused = set(parameters) - used
    if unused:
        raise ValueError(
            f"{source}: unused widget parameters: {', '.join(sorted(unused))}"
        )


def _read_fragment(widget_path: Path) -> ET.Element:
    try:
        fragment = ET.parse(widget_path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ValueError(f"cannot load XML widget '{widget_path}': {error}") from error
    if fragment.tag != "fragment":
        raise ValueError(f"XML widget '{widget_path}' root must be <fragment>")
    return fragment


def _rebase_images(
    fragment: ET.Element,
    widget_path: Path,
    screen_dir: Path,
    dependencies: set[Path] | None,
) -> None:
    for image in fragment.iter("lv_image"):
        source = image.get("src")
        if not source or Path(source).is_absolute():
            continue
        asset_path = (widget_path.parent / source).resolve()
        if dependencies is not None:
            dependencies.add(asset_path)
        image.set("src", Path(os.path.relpath(asset_path, screen_dir)).as_posix())


def _transform_editor_instance(
    fragment: ET.Element, include: ET.Element, source: Path
) -> None:
    if "editor_id" not in include.attrib:
        return

    names = (
        "editor_x",
        "editor_y",
        "editor_width",
        "editor_height",
        "editor_base_x",
        "editor_base_y",
        "editor_base_width",
        "editor_base_height",
    )
    try:
        values = {name: float(include.attrib[name]) for name in names}
    except (KeyError, ValueError) as error:
        raise ValueError(f"{source}: editor instance has invalid geometry") from error

    if values["editor_width"] <= 0 or values["editor_height"] <= 0:
        raise ValueError(f"{source}: editor instance size must be positive")
    if values["editor_base_width"] <= 0 or values["editor_base_height"] <= 0:
        raise ValueError(f"{source}: editor module bounds must be positive")

    scale_x = values["editor_width"] / values["editor_base_width"]
    scale_y = values["editor_height"] / values["editor_base_height"]
    font_scale = min(scale_x, scale_y)
    for element in fragment.iter():
        for name, scale, origin, target in (
            ("x", scale_x, values["editor_base_x"], values["editor_x"]),
            ("y", scale_y, values["editor_base_y"], values["editor_y"]),
        ):
            raw = element.get(name)
            if raw is not None:
                try:
                    element.set(name, str(round(target + (float(raw) - origin) * scale)))
                except ValueError as error:
                    raise ValueError(
                        f"{source}: editor module has non-numeric {name}"
                    ) from error

        for name, scale in (
            ("width", scale_x),
            ("height", scale_y),
            ("font_size", font_scale),
            ("ring_width", font_scale),
        ):
            raw = element.get(name)
            if raw is not None:
                try:
                    element.set(name, str(max(1, round(float(raw) * scale))))
                except ValueError as error:
                    raise ValueError(
                        f"{source}: editor module has non-numeric {name}"
                    ) from error


def _expand_include(
    include: ET.Element,
    source: Path,
    screen_dir: Path,
    stack: tuple[Path, ...],
    dependencies: set[Path] | None,
) -> list[ET.Element]:
    if len(include):
        raise ValueError("<zmk_include> cannot have child elements")
    include_source = include.get("src")
    if not include_source:
        raise ValueError("<zmk_include> needs a src attribute")
    widget_path = (source.parent / include_source).resolve()
    if dependencies is not None:
        dependencies.add(widget_path)
    if widget_path in stack:
        cycle = " -> ".join(str(path) for path in (*stack, widget_path))
        raise ValueError(f"cyclic XML widget include: {cycle}")

    fragment = _read_fragment(widget_path)
    parameters = {
        name: value
        for name, value in include.attrib.items()
        if name != "src"
        and name not in EDITOR_ATTRIBUTES
        and not name.startswith("editor_")
    }
    template_parameters = {
        parameter
        for element in fragment.iter()
        for value in (*element.attrib.values(), element.text or "")
        for parameter in PARAMETER.findall(value)
    }
    if "label" not in template_parameters:
        parameters.pop("label", None)
    _substitute(fragment, parameters, widget_path)
    _transform_editor_instance(fragment, include, widget_path)
    _rebase_images(fragment, widget_path, screen_dir, dependencies)
    _expand_children(
        fragment, widget_path, screen_dir, (*stack, widget_path), dependencies
    )
    replacements = list(fragment)
    if not replacements:
        raise ValueError(f"XML widget '{widget_path}' has no elements")
    return replacements


def _replace_include(
    parent: ET.Element, include: ET.Element, replacements: list[ET.Element]
) -> None:
    index = tuple(parent).index(include)
    parent.remove(include)
    for offset, replacement in enumerate(replacements):
        parent.insert(index + offset, replacement)
    replacements[-1].tail = (replacements[-1].tail or "") + (include.tail or "")


def _expand_children(
    parent: ET.Element,
    source: Path,
    screen_directory: Path,
    stack: tuple[Path, ...],
    dependencies: set[Path] | None,
) -> None:
    for child in tuple(parent):
        if child.tag == "zmk_include":
            replacements = _expand_include(
                child, source, screen_directory, stack, dependencies
            )
            _replace_include(parent, child, replacements)
        else:
            _expand_children(child, source, screen_directory, stack, dependencies)


def expand_screen_file(screen_path: Path, dependencies: set[Path] | None = None) -> str:
    """Return a screen with all reusable widget fragments expanded inline."""
    screen_path = screen_path.resolve()
    if dependencies is not None:
        dependencies.add(screen_path)
    try:
        root = ET.parse(screen_path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ValueError(f"cannot load XML screen '{screen_path}': {error}") from error
    if dependencies is not None:
        for image in root.iter("lv_image"):
            source = image.get("src")
            if source and not Path(source).is_absolute():
                dependencies.add((screen_path.parent / source).resolve())
    _expand_children(
        root, screen_path, screen_path.parent, (screen_path,), dependencies
    )
    return ET.tostring(root, encoding="unicode")

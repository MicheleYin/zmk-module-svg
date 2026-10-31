# ZMK LVGL XML Status Screens

[![Build](https://github.com/MicheleYin/zmk-module-svg/actions/workflows/zmk-module.yml/badge.svg?branch=main)](https://github.com/MicheleYin/zmk-module-svg/actions/workflows/zmk-module.yml)

XML-authored status screens for Nice!View (160×68) and 128×32 SSD1306 OLEDs.
Firmware uses generated LVGL C; SVG, PNG, and GIF artwork is processed offline
and embedded during generation.

- XML authoring: [docs/widget-authoring-xml.md](docs/widget-authoring-xml.md)
- Paired preview gallery: [docs/ui/gallery](docs/ui/gallery/)
- Build and contributor notes: [AGENTS.md](AGENTS.md)
- Agent / contributor commands: [AGENTS.md](AGENTS.md)

WPM is not enabled by this module, but remains in the optional status packet if
another configuration enables it.

## Screen Gallery

The paired previews use LVGL's native XML renderer and side-specific screen sources.
Each row shows central and peripheral status values in the matching left/right layout.

| Configuration | Left half | Right half |
| --- | --- | --- |
| Nice!View (160×68) | <img src="docs/ui/gallery/nice-view-left.png" alt="Left Nice!View screen" width="320"> | <img src="docs/ui/gallery/nice-view-right.png" alt="Right Nice!View screen" width="320"> |
| OLED (128×32) | <img src="docs/ui/gallery/oled-left.png" alt="Left OLED screen" width="320"> | <img src="docs/ui/gallery/oled-right.png" alt="Right OLED screen" width="320"> |

<!-- ARTWORK GALLERY START -->
## Artwork Dither Gallery

Put raster artwork in `docs/ui/artwork/`, then run:

```sh
uv run --isolated --with-requirements tools/requirements.txt python tools/artwork_gallery.py
```

Each comparison is cropped to the 160×68 Nice!View screen and shows the available conversion modes left to right: none, Floyd–Steinberg, Atkinson, and Bayer. The links open the individual PNG or animated GIF output and the generated XML screen sample.

| Artwork | Dither comparison | Screen sample | Individual modes |
| --- | --- | --- | --- |
| [blossom-meadow.jpeg](docs/ui/artwork/blossom-meadow.jpeg) | <img src="docs/ui/gallery/artwork/blossom-meadow/comparison.png" alt="blossom-meadow.jpeg: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-blossom-meadow.xml) | [none](docs/ui/gallery/artwork/blossom-meadow/none.png) · [floyd-steinberg](docs/ui/gallery/artwork/blossom-meadow/floyd-steinberg.png) · [atkinson](docs/ui/gallery/artwork/blossom-meadow/atkinson.png) · [bayer](docs/ui/gallery/artwork/blossom-meadow/bayer.png) |
| [cloud-cat.jpeg](docs/ui/artwork/cloud-cat.jpeg) | <img src="docs/ui/gallery/artwork/cloud-cat/comparison.png" alt="cloud-cat.jpeg: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-cloud-cat.xml) | [none](docs/ui/gallery/artwork/cloud-cat/none.png) · [floyd-steinberg](docs/ui/gallery/artwork/cloud-cat/floyd-steinberg.png) · [atkinson](docs/ui/gallery/artwork/cloud-cat/atkinson.png) · [bayer](docs/ui/gallery/artwork/cloud-cat/bayer.png) |
| [moonlit-hillside.jpeg](docs/ui/artwork/moonlit-hillside.jpeg) | <img src="docs/ui/gallery/artwork/moonlit-hillside/comparison.png" alt="moonlit-hillside.jpeg: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-moonlit-hillside.xml) | [none](docs/ui/gallery/artwork/moonlit-hillside/none.png) · [floyd-steinberg](docs/ui/gallery/artwork/moonlit-hillside/floyd-steinberg.png) · [atkinson](docs/ui/gallery/artwork/moonlit-hillside/atkinson.png) · [bayer](docs/ui/gallery/artwork/moonlit-hillside/bayer.png) |
| [pixel-astronaut.webp](docs/ui/artwork/pixel-astronaut.webp) | <img src="docs/ui/gallery/artwork/pixel-astronaut/comparison.png" alt="pixel-astronaut.webp: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-pixel-astronaut.xml) | [none](docs/ui/gallery/artwork/pixel-astronaut/none.gif) · [floyd-steinberg](docs/ui/gallery/artwork/pixel-astronaut/floyd-steinberg.gif) · [atkinson](docs/ui/gallery/artwork/pixel-astronaut/atkinson.gif) · [bayer](docs/ui/gallery/artwork/pixel-astronaut/bayer.gif) |
| [pixel-cat.gif](docs/ui/artwork/pixel-cat.gif) | <img src="docs/ui/gallery/artwork/pixel-cat/comparison.png" alt="pixel-cat.gif: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-pixel-cat.xml) | [none](docs/ui/gallery/artwork/pixel-cat/none.gif) · [floyd-steinberg](docs/ui/gallery/artwork/pixel-cat/floyd-steinberg.gif) · [atkinson](docs/ui/gallery/artwork/pixel-cat/atkinson.gif) · [bayer](docs/ui/gallery/artwork/pixel-cat/bayer.gif) |
| [sakura-village.jpg](docs/ui/artwork/sakura-village.jpg) | <img src="docs/ui/gallery/artwork/sakura-village/comparison.png" alt="sakura-village.jpg: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-sakura-village.xml) | [none](docs/ui/gallery/artwork/sakura-village/none.png) · [floyd-steinberg](docs/ui/gallery/artwork/sakura-village/floyd-steinberg.png) · [atkinson](docs/ui/gallery/artwork/sakura-village/atkinson.png) · [bayer](docs/ui/gallery/artwork/sakura-village/bayer.png) |
| [shrine-garden.jpeg](docs/ui/artwork/shrine-garden.jpeg) | <img src="docs/ui/gallery/artwork/shrine-garden/comparison.png" alt="shrine-garden.jpeg: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-shrine-garden.xml) | [none](docs/ui/gallery/artwork/shrine-garden/none.png) · [floyd-steinberg](docs/ui/gallery/artwork/shrine-garden/floyd-steinberg.png) · [atkinson](docs/ui/gallery/artwork/shrine-garden/atkinson.png) · [bayer](docs/ui/gallery/artwork/shrine-garden/bayer.png) |
| [spring-lane.jpg](docs/ui/artwork/spring-lane.jpg) | <img src="docs/ui/gallery/artwork/spring-lane/comparison.png" alt="spring-lane.jpg: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-spring-lane.xml) | [none](docs/ui/gallery/artwork/spring-lane/none.png) · [floyd-steinberg](docs/ui/gallery/artwork/spring-lane/floyd-steinberg.png) · [atkinson](docs/ui/gallery/artwork/spring-lane/atkinson.png) · [bayer](docs/ui/gallery/artwork/spring-lane/bayer.png) |
| [sunset-drive.gif](docs/ui/artwork/sunset-drive.gif) | <img src="docs/ui/gallery/artwork/sunset-drive/comparison.png" alt="sunset-drive.gif: all dithering modes" width="640"> | [Screen XML](docs/ui/samples/nice-view-artwork-sunset-drive.xml) | [none](docs/ui/gallery/artwork/sunset-drive/none.gif) · [floyd-steinberg](docs/ui/gallery/artwork/sunset-drive/floyd-steinberg.gif) · [atkinson](docs/ui/gallery/artwork/sunset-drive/atkinson.gif) · [bayer](docs/ui/gallery/artwork/sunset-drive/bayer.gif) |
<!-- ARTWORK GALLERY END -->

Build the LVGL renderer and regenerate the gallery after changing screens, widgets,
or artwork:

```sh
emcmake cmake -S tools/lvgl_wasm -B build/lvgl_wasm
cmake --build build/lvgl_wasm
uv run --isolated --with-requirements tools/requirements.txt python tools/render_xml_gallery.py
```

## Interactive Screen Design

Launch the artwork placement editor, visual screen designer, and live XML preview
together:

```sh
uv run --isolated --with-requirements tools/requirements.txt \
    python tools/artwork_gallery.py --interactive
```

In **Screen designer**, select the screen type and the half to edit; both halves
stay visible side by side. Choose **Image background** from **Widget type** to
add one or more full-screen backgrounds, or choose a status widget. Resize items
with the canvas handle or the size fields. For images, choose crop-to-fill or
fit-entire-image, adjust the crop position, rotation, and dithering. Save the
design to XML or build firmware screens and the paired preview gallery.
The **XML preview** tab can inspect standard screens and generated artwork samples
with interactive status fields.

## XML Tooling

Screen sources and reusable widgets live under `docs/ui/`. Use the same field catalog
for validation, previews, and firmware generation. Live preview watches screen XML,
nested widgets, and referenced artwork and refreshes when those files change.
GIF artwork is converted offline into monochrome animation frames; the generated
gallery includes frame contact sheets. See [XML authoring](docs/widget-authoring-xml.md)
for frame limits, sample PNG/GIF screens, and image-only dithering choices. Compare
algorithms quickly with:

```sh
uv run --isolated --with-requirements tools/requirements.txt \
    python tools/render_xml_gallery.py --dither atkinson
```

```sh
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_xml.py validate docs/ui/screens/nice-view-left.xml
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_xml.py generate docs/ui/screens/nice-view-left.xml --output-dir src/generated_xml/nice_view_left
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_xml.py preview docs/ui/screens/nice-view-left.xml --values tools/sample_status.central.json --role central --output /tmp/nice_view_left.png
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_xml_live.py docs/ui/screens/nice-view-left.xml
uv run --isolated --with-requirements tools/requirements.txt python tools/nice_view_xml_live.py docs/ui/screens/nice-view-left.xml --right-screen docs/ui/screens/nice-view-right.xml
uv run --isolated --with-requirements tools/requirements.txt python tools/render_xml_gallery.py
uv run --isolated --with-requirements tools/requirements.txt python -m unittest test_nice_view_xml
```

| Screen | Generate `--output-dir` |
| --- | --- |
| `docs/ui/screens/nice-view-left.xml` | `src/generated_xml/nice_view_left` |
| `docs/ui/screens/nice-view-right.xml` | `src/generated_xml/nice_view_right` |
| `docs/ui/screens/oled-left.xml` | `src/generated_xml/oled_left` |
| `docs/ui/screens/oled-right.xml` | `src/generated_xml/oled_right` |

```conf
CONFIG_ZMK_SVG=y
CONFIG_ZMK_SVG_SCREEN=y
```

WPM remains available when `CONFIG_ZMK_WPM` is enabled.

### Different themes on each half

Each half is built as a separate firmware image, so it can use a different screen theme. To use the day screen on the left and night screen on the right, enable the XML screen in both images and select one theme per image:

```conf
# Both halves
CONFIG_ZMK_SVG=y
CONFIG_ZMK_SVG_SCREEN=y
CONFIG_NICE_VIEW_WIDGET_STATUS=n
```

```conf
# Left Nice!View uses the left XML screen
CONFIG_ZMK_SVG_THEME_LEFT=y
```

```conf
# Right Nice!View uses the right XML screen
CONFIG_ZMK_SVG_THEME_RIGHT=y
```

## Compatibility and setup

This module is currently supported with MicheleYin's ZMK fork on the `feature/nice-view` branch. It depends on that branch's split-BLE status synchronization and peripheral battery level/charge-state fetching, which let both Nice!View displays show central-owned status and the remote half's battery data. The module enables these fork-specific Kconfig features, so upstream ZMK or another revision is not a supported replacement.

Pin both ZMK and this module in your configuration's `config/west.yml`:

```yaml
manifest:
    projects:
        - name: zmk
            url: https://github.com/MicheleYin/zmk.git
            revision: feature/nice-view
            import: app/west.yml
        - name: zmk-module-svg
            url: https://github.com/MicheleYin/zmk-module-svg
            revision: feature/nice-view
```

Update the projects after changing the manifest:

```sh
west update
```

For a new West workspace, initialize it from your configuration repository, then update and export Zephyr:

```sh
west init -l config
west update
west zephyr-export
```

## Use the Module

Enable ZMK SVG in the configuration used by each display:

```conf
CONFIG_ZMK_SVG=y
```

For Nice!View shields only, also disable the built-in Nice!View status screen:

```conf
CONFIG_NICE_VIEW_WIDGET_STATUS=n
```

### Nice!View color polarity

Nice!View uses black for a set pixel and white for a clear pixel. ZMK SVG defaults to black artwork on a white background; leave `CONFIG_NICE_VIEW_WIDGET_INVERTED` unset for this usual appearance. You can reverse black and white by enabling the Nice!View option in each half's configuration:

```conf
CONFIG_NICE_VIEW_WIDGET_INVERTED=y
```

Inverted white-on-black LVGL text can appear thinner. If that is undesirable, leave the inversion option unset. If it must be enabled for another part of the display but ZMK SVG should stay black-on-white, set this module option in each half's configuration:

```conf
CONFIG_ZMK_SVG_WHITE_BACKGROUND=y
```

To highlight the right side in the split indicator, set this only in the right half's configuration:

```conf
CONFIG_ZMK_SVG_RIGHT_HALF=y
```

Keep `nice_view` in the shield list for Nice!View panels. For SSD1306 panels, enable `ZMK_DISPLAY` in the shield configuration. The module requires `ZMK_DISPLAY` and Settings; native layouts support 160 x 68 and 128 x 32. SVG headers are selected at build time from the chosen display's Devicetree dimensions, and a mismatched header stops the build. Split BLE status synchronization is selected automatically for split BLE builds.

The XML screen is selected by display dimensions and physical side: 160×68 uses the left/right Nice!View screen, while 128×32 uses the left/right OLED screen. Set `CONFIG_ZMK_SVG_RIGHT_HALF=y` on the physical right half. For Nice!View, `CONFIG_ZMK_SVG_THEME_LEFT=y` or `CONFIG_ZMK_SVG_THEME_RIGHT=y` can force a side layout. `CONFIG_ZMK_SVG_WHITE_BACKGROUND=y` keeps empty areas white even when legacy Nice!View widget inversion is enabled. See [LVGL XML authoring](docs/widget-authoring-xml.md) for the complete source-to-firmware workflow. Version-1 saved layout records fall back to the version-2 defaults.

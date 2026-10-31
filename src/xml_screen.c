/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/display.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

#include <zmk/split/bluetooth/status.h>
#include <zmk/keymap.h>
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
#include <zmk/usb.h>
#endif
#if IS_ENABLED(CONFIG_ZMK_WPM)
#include <zmk/wpm.h>
#endif

#include <lvgl.h>

#if IS_ENABLED(CONFIG_ZMK_SVG_THEME_LEFT)
#if DT_PROP(DT_CHOSEN(zephyr_display), width) != 160 ||                                            \
    DT_PROP(DT_CHOSEN(zephyr_display), height) != 68
#error "The left Nice!View XML screen requires a 160x68 display"
#endif
#include "generated_xml/nice_view_left/status_screen_gen.h"
#elif IS_ENABLED(CONFIG_ZMK_SVG_THEME_RIGHT)
#if DT_PROP(DT_CHOSEN(zephyr_display), width) != 160 ||                                            \
    DT_PROP(DT_CHOSEN(zephyr_display), height) != 68
#error "The right Nice!View XML screen requires a 160x68 display"
#endif
#include "generated_xml/nice_view_right/status_screen_gen.h"
#elif DT_PROP(DT_CHOSEN(zephyr_display), width) == 128 &&                                          \
    DT_PROP(DT_CHOSEN(zephyr_display), height) == 32
#if IS_ENABLED(CONFIG_ZMK_SVG_RIGHT_HALF)
#include "generated_xml/oled_right/status_screen_gen.h"
#else
#include "generated_xml/oled_left/status_screen_gen.h"
#endif
#elif DT_PROP(DT_CHOSEN(zephyr_display), width) == 160 &&                                          \
    DT_PROP(DT_CHOSEN(zephyr_display), height) == 68
#if IS_ENABLED(CONFIG_ZMK_SVG_RIGHT_HALF)
#include "generated_xml/nice_view_right/status_screen_gen.h"
#else
#include "generated_xml/nice_view_left/status_screen_gen.h"
#endif
#else
#error "Automatic LVGL XML theme supports 160x68 and 128x32 displays"
#endif

BUILD_ASSERT(ZMK_NVP_SVG_WIDTH == DT_PROP(DT_CHOSEN(zephyr_display), width),
             "Generated XML width must match the selected display");
BUILD_ASSERT(ZMK_NVP_SVG_HEIGHT == DT_PROP(DT_CHOSEN(zephyr_display), height),
             "Generated XML height must match the selected display");

#include "xml_screen.h"

LOG_MODULE_REGISTER(zmk_xml_screen, CONFIG_ZMK_LOG_LEVEL);

struct field_value {
    bool valid;
    bool is_text;
    int32_t number;
    const char *text;
};

struct xml_animation_playback {
    lv_obj_t *image;
    const struct zmk_nvp_svg_animation *animation;
    lv_timer_t *timer;
    uint16_t frame_index;
    uint32_t completed_repeats;
    bool paused;
    struct xml_animation_playback *next;
};

static lv_obj_t *screen;
static lv_obj_t *binding_objects[ZMK_NVP_SVG_BINDING_COUNT];
static struct xml_animation_playback *xml_animations;

static void animation_timer_cb(lv_timer_t *timer) {
    struct xml_animation_playback *playback = lv_timer_get_user_data(timer);
    uint16_t next_frame = playback->frame_index + 1;
    if (next_frame >= playback->animation->frame_count) {
        if (playback->animation->repeat_count != 0 &&
            playback->completed_repeats + 1 >= playback->animation->repeat_count) {
            lv_timer_delete(timer);
            playback->timer = NULL;
            return;
        }
        playback->completed_repeats++;
        next_frame = 0;
    }

    playback->frame_index = next_frame;
    lv_image_set_src(playback->image, playback->animation->frames[next_frame]);
    lv_timer_set_period(timer, playback->animation->durations_ms[next_frame]);
}

static void animation_delete_event(lv_event_t *event) {
    struct xml_animation_playback *playback = lv_event_get_user_data(event);
    struct xml_animation_playback **current = &xml_animations;
    while (*current && *current != playback) {
        current = &(*current)->next;
    }
    if (*current == playback) {
        *current = playback->next;
    }
    if (playback->timer) {
        lv_timer_delete(playback->timer);
    }
    lv_free(playback);
}

void zmk_nvp_xml_animation_attach(
    lv_obj_t *image, const struct zmk_nvp_svg_animation *animation, bool initially_paused) {
    if (!image || !animation || !animation->frames || animation->frame_count == 0) {
        return;
    }

    lv_image_set_src(image, animation->frames[0]);
    if (animation->frame_count < 2) {
        return;
    }

    struct xml_animation_playback *playback = lv_malloc(sizeof(*playback));
    if (!playback) {
        LOG_WRN("Unable to allocate GIF playback state; showing its first frame");
        return;
    }
    *playback = (struct xml_animation_playback){
        .image = image,
        .animation = animation,
        .paused = initially_paused,
        .next = xml_animations,
    };
    playback->timer = lv_timer_create(animation_timer_cb, animation->durations_ms[0], playback);
    if (!playback->timer ||
        !lv_obj_add_event_cb(image, animation_delete_event, LV_EVENT_DELETE, playback)) {
        if (playback->timer) {
            lv_timer_delete(playback->timer);
        }
        lv_free(playback);
        LOG_WRN("Unable to start GIF playback; showing its first frame");
        return;
    }
    xml_animations = playback;
    if (initially_paused) {
        lv_timer_pause(playback->timer);
    }
}

lv_obj_t *zmk_nvp_xml_animation_create(
    lv_obj_t *parent, const struct zmk_nvp_svg_animation *animation, int16_t x, int16_t y,
    bool initially_paused) {
    if (!parent || !animation) {
        return NULL;
    }
    lv_obj_t *image = lv_image_create(parent);
    lv_obj_set_pos(image, x, y);
    zmk_nvp_xml_animation_attach(image, animation, initially_paused);
    return image;
}

void zmk_nvp_xml_animation_set_paused(lv_obj_t *image, bool paused) {
    for (struct xml_animation_playback *playback = xml_animations; playback;
         playback = playback->next) {
        if (playback->image != image || playback->paused == paused) {
            continue;
        }
        playback->paused = paused;
        if (playback->timer) {
            if (paused) {
                lv_timer_pause(playback->timer);
            } else {
                lv_timer_resume(playback->timer);
            }
        }
        return;
    }
}

static lv_color_t foreground_color(void) {
    bool inverted = IS_ENABLED(CONFIG_NICE_VIEW_WIDGET_INVERTED) &&
                    !IS_ENABLED(CONFIG_ZMK_SVG_WHITE_BACKGROUND);
    return inverted ? lv_color_white() : lv_color_black();
}

static lv_color_t background_color(void) {
    bool inverted = IS_ENABLED(CONFIG_NICE_VIEW_WIDGET_INVERTED) &&
                    !IS_ENABLED(CONFIG_ZMK_SVG_WHITE_BACKGROUND);
    return inverted ? lv_color_black() : lv_color_white();
}

static uint8_t display_role(void) {
#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    return 2;
#else
    return 1;
#endif
}

static bool remote_fields_available(void) {
#if IS_ENABLED(CONFIG_ZMK_SPLIT) && !IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    return true;
#else
    return false;
#endif
}

static struct field_value numeric_value(int32_t number) {
    return (struct field_value){.valid = true, .number = number};
}

static struct field_value string_value(const char *text) {
    return (struct field_value){.valid = true, .is_text = true, .text = text};
}

static struct field_value battery_charge_value(enum zmk_battery_charge_state charge_state) {
    switch (charge_state) {
    case ZMK_BATTERY_CHARGE_STATE_CHARGING:
        return string_value("charging");
    case ZMK_BATTERY_CHARGE_STATE_DISCHARGING:
        return string_value("discharging");
    case ZMK_BATTERY_CHARGE_STATE_FULL:
        return string_value("full");
    default:
        return string_value("unknown");
    }
}

static struct field_value read_field(const char *field_id,
                                     const struct zmk_nvp_screen_state *state) {
    if (strcmp(field_id, "battery.left.percent") == 0 ||
        strcmp(field_id, "battery.right.percent") == 0) {
        bool battery_is_right = strcmp(field_id, "battery.right.percent") == 0;
        bool central_is_right = IS_ENABLED(CONFIG_ZMK_SVG_CENTRAL_RIGHT_HALF);
        return read_field(battery_is_right == central_is_right ? "battery.central.percent"
                                                               : "battery.peripheral.percent",
                          state);
    }
    if (strcmp(field_id, "battery.left.charge") == 0 ||
        strcmp(field_id, "battery.right.charge") == 0) {
        bool battery_is_right = strcmp(field_id, "battery.right.charge") == 0;
        bool central_is_right = IS_ENABLED(CONFIG_ZMK_SVG_CENTRAL_RIGHT_HALF);
        return read_field(battery_is_right == central_is_right ? "battery.central.charge"
                                                               : "battery.peripheral.charge",
                          state);
    }
    if (strcmp(field_id, "battery.central.percent") == 0) {
        if (remote_fields_available() && !state->has_remote_status) {
            return (struct field_value){0};
        }
        return state->central_battery_level <= 100 ? numeric_value(state->central_battery_level)
                                                   : (struct field_value){0};
    }
    if (strcmp(field_id, "battery.central.charge") == 0) {
        return battery_charge_value(state->central_charge_state);
    }
    if (strcmp(field_id, "battery.peripheral.percent") == 0) {
        return state->peripheral_battery_level <= 100
                   ? numeric_value(state->peripheral_battery_level)
                   : (struct field_value){0};
    }
    if (strcmp(field_id, "battery.peripheral.charge") == 0) {
        return battery_charge_value(state->peripheral_charge_state);
    }
    if (strcmp(field_id, "layer.index") == 0) {
        if (remote_fields_available() && !state->has_remote_status) {
            return (struct field_value){0};
        }
        return numeric_value(state->active_layer);
    }
    if (strcmp(field_id, "layer.name") == 0) {
        if (remote_fields_available() && !state->has_remote_status) {
            return (struct field_value){0};
        }
#if !IS_ENABLED(CONFIG_ZMK_SPLIT) || IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
        zmk_keymap_layer_id_t layer_id =
            zmk_keymap_layer_index_to_id((zmk_keymap_layer_index_t)state->active_layer);
        const char *name = zmk_keymap_layer_name(layer_id);
        return name ? string_value(name) : (struct field_value){0};
#else
        return (struct field_value){0};
#endif
    }
    if (strcmp(field_id, "output.selected") == 0) {
        if (remote_fields_available() && !state->has_remote_status) {
            return (struct field_value){0};
        }
        switch (state->output) {
        case ZMK_SPLIT_BLE_STATUS_OUTPUT_USB:
            return string_value("usb");
        case ZMK_SPLIT_BLE_STATUS_OUTPUT_BLE:
            return string_value("ble");
        default:
            return string_value("none");
        }
    }
    if (strcmp(field_id, "ble.active_profile") == 0) {
        if (remote_fields_available() && !state->has_remote_status) {
            return (struct field_value){0};
        }
        return numeric_value(state->active_ble_profile == ZMK_SPLIT_BLE_STATUS_NO_PROFILE
                                 ? -1
                                 : state->active_ble_profile);
    }
    if (strcmp(field_id, "ble.profile_count") == 0) {
        if (remote_fields_available() && !state->has_remote_status) {
            return (struct field_value){0};
        }
        return numeric_value(state->ble_profile_count);
    }
    if (strcmp(field_id, "ble.connected_profiles") == 0) {
        if (remote_fields_available() && !state->has_remote_status) {
            return (struct field_value){0};
        }
        return numeric_value(state->connected_ble_profiles);
    }
    if (strcmp(field_id, "ble.bonded_profiles") == 0) {
        if (remote_fields_available() && !state->has_remote_status) {
            return (struct field_value){0};
        }
        return numeric_value(state->bonded_ble_profiles);
    }
    if (strcmp(field_id, "usb.powered") == 0) {
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
        return string_value(zmk_usb_is_powered() ? "true" : "false");
#else
        return (struct field_value){0};
#endif
    }
    if (strcmp(field_id, "usb.hid_ready") == 0) {
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
        return string_value(zmk_usb_is_hid_ready() ? "true" : "false");
#else
        return (struct field_value){0};
#endif
    }
    if (strcmp(field_id, "wpm.current") == 0) {
#if IS_ENABLED(CONFIG_ZMK_WPM)
        return numeric_value(state->wpm_current);
#else
        return (struct field_value){0};
#endif
    }
    if (strcmp(field_id, "display.half") == 0) {
        return string_value(IS_ENABLED(CONFIG_ZMK_SVG_RIGHT_HALF) ? "right" : "left");
    }
    if (strcmp(field_id, "split.connected") == 0) {
        return string_value(state->split_connected ? "true" : "false");
    }
    return (struct field_value){0};
}

static bool field_matches(struct field_value value, const struct zmk_nvp_svg_binding *binding) {
    if (!value.valid) {
        return false;
    }
    if (strcmp(binding->when, "set") == 0 || strcmp(binding->when, "clear") == 0) {
        if (value.is_text) {
            return false;
        }
        bool bit_set = (value.number & BIT(binding->match_bit)) != 0;
        return bit_set == (strcmp(binding->when, "set") == 0);
    }
    if (value.is_text) {
        return strcmp(value.text, binding->when) == 0;
    }
    char *end;
    long expected_number = strtol(binding->when, &end, 10);
    return end != binding->when && *end == '\0' && value.number == expected_number;
}

static const lv_font_t *binding_font(const struct zmk_nvp_svg_binding *binding) {
    if (binding->font_size >= 16) {
        return &lv_font_montserrat_20;
    }
    if (binding->font_size > 8) {
        return &lv_font_montserrat_12;
    }
    if (strstr(binding->font_family, "monospace")) {
        return &lv_font_unscii_8;
    }
    return &lv_font_montserrat_8;
}

static void place_text(lv_obj_t *label, const struct zmk_nvp_svg_binding *binding) {
    lv_coord_t x = binding->x;
    lv_coord_t y = binding->y - binding->font_size;
    lv_coord_t width = ZMK_NVP_SVG_WIDTH;
    lv_coord_t height = MAX(binding->font_size + 2, 10);
    lv_text_align_t align = LV_TEXT_ALIGN_LEFT;
    if (binding->width > 0) {
        width = binding->width;
        height = binding->height > 0 ? binding->height : height;
        y = binding->y + MAX((height - lv_font_get_line_height(binding_font(binding))) / 2, 0);
        if (strcmp(binding->anchor, "middle") == 0) {
            align = LV_TEXT_ALIGN_CENTER;
        } else if (strcmp(binding->anchor, "end") == 0) {
            align = LV_TEXT_ALIGN_RIGHT;
        }
    } else if (strcmp(binding->anchor, "middle") == 0) {
        x -= ZMK_NVP_SVG_WIDTH / 2;
        align = LV_TEXT_ALIGN_CENTER;
    } else if (strcmp(binding->anchor, "end") == 0) {
        x -= ZMK_NVP_SVG_WIDTH;
        align = LV_TEXT_ALIGN_RIGHT;
    }
    lv_obj_set_pos(label, x, y);
    lv_obj_set_size(label, width, height);
    lv_obj_set_style_text_align(label, align, LV_PART_MAIN);
}

static lv_obj_t *create_binding_object(const struct zmk_nvp_svg_binding *binding) {
    if ((binding->roles & display_role()) == 0) {
        return NULL;
    }

    if (binding->renderer == ZMK_NVP_SVG_RENDER_VISIBLE) {
        if (binding->asset_index < ZMK_NVP_SVG_VISIBLE_ASSET_COUNT) {
            lv_obj_t *image = lv_image_create(screen);
            lv_image_set_src(image, zmk_nvp_svg_visible_assets[binding->asset_index]);
            lv_obj_set_pos(image, binding->x, binding->y);
            lv_obj_add_flag(image, LV_OBJ_FLAG_HIDDEN);
            uint8_t animation_index =
                zmk_nvp_svg_visible_animation_indices[binding->asset_index];
            if (animation_index < ZMK_NVP_SVG_ANIMATION_COUNT) {
                zmk_nvp_xml_animation_attach(
                    image, &zmk_nvp_svg_animations[animation_index], true);
            }
            return image;
        }
        lv_obj_t *label = lv_label_create(screen);
        lv_label_set_text(label, binding->prefix);
        lv_obj_set_pos(label, binding->x, binding->y);
        lv_obj_set_style_text_color(label, foreground_color(), LV_PART_MAIN);
        lv_obj_add_flag(label, LV_OBJ_FLAG_HIDDEN);
        return label;
    }

    if (binding->renderer == ZMK_NVP_SVG_RENDER_RING) {
        lv_obj_t *arc = lv_arc_create(screen);
        lv_coord_t padding = (binding->ring_width + 1) / 2;
        lv_coord_t extent = binding->ring_radius + padding;
        lv_obj_set_pos(arc, binding->x - extent, binding->y - extent);
        lv_obj_set_size(arc, 2 * extent, 2 * extent);
        lv_obj_set_style_bg_opa(arc, LV_OPA_TRANSP, LV_PART_MAIN);
        lv_obj_set_style_border_width(arc, 0, LV_PART_MAIN);
        lv_obj_set_style_pad_all(arc, padding, LV_PART_MAIN);
        lv_obj_set_style_arc_opa(arc, LV_OPA_TRANSP, LV_PART_MAIN);
        lv_obj_set_style_arc_width(arc, binding->ring_width, LV_PART_MAIN);
        lv_obj_set_style_pad_all(arc, 0, LV_PART_INDICATOR);
        lv_obj_set_style_arc_color(arc, binding->color ? background_color() : foreground_color(),
                                   LV_PART_INDICATOR);
        lv_obj_set_style_arc_opa(arc, LV_OPA_COVER, LV_PART_INDICATOR);
        lv_obj_set_style_arc_width(arc, binding->ring_width, LV_PART_INDICATOR);
        lv_obj_set_style_arc_rounded(arc, binding->ring_rounded, LV_PART_INDICATOR);
        lv_obj_set_style_bg_opa(arc, LV_OPA_TRANSP, LV_PART_KNOB);
        lv_obj_set_style_border_width(arc, 0, LV_PART_KNOB);
        lv_obj_set_style_pad_all(arc, 0, LV_PART_KNOB);
        lv_arc_set_bg_angles(arc, 0, 359);
        lv_arc_set_rotation(arc, 270);
        lv_arc_set_mode(arc, LV_ARC_MODE_NORMAL);
        lv_arc_set_range(arc, 0, 100);
        lv_arc_set_value(arc, 0);
        lv_obj_clear_flag(arc, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_flag(arc, LV_OBJ_FLAG_HIDDEN);
        return arc;
    }

    if (binding->renderer == ZMK_NVP_SVG_RENDER_BAR) {
        lv_obj_t *bar = lv_obj_create(screen);
        lv_obj_set_pos(bar, binding->x, binding->y);
        lv_obj_set_size(bar, binding->width, binding->height);
        lv_obj_set_style_bg_color(bar, binding->color ? background_color() : foreground_color(),
                                  LV_PART_MAIN);
        lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_border_width(bar, 0, LV_PART_MAIN);
        lv_obj_set_style_pad_all(bar, 0, LV_PART_MAIN);
        lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);
        return bar;
    }

    lv_obj_t *label = lv_label_create(screen);
    place_text(label, binding);
    lv_obj_set_style_text_color(label, binding->color ? background_color() : foreground_color(),
                                LV_PART_MAIN);
    lv_obj_set_style_text_font(label, binding_font(binding), LV_PART_MAIN);
    return label;
}

lv_obj_t *zmk_nvp_xml_screen_create(void) {
    const struct device *display_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_display));
    struct display_capabilities capabilities;
    if (!device_is_ready(display_device)) {
        LOG_ERR("Display device is not ready");
        return NULL;
    }
    display_get_capabilities(display_device, &capabilities);
    if (capabilities.x_resolution != ZMK_NVP_SVG_WIDTH ||
        capabilities.y_resolution != ZMK_NVP_SVG_HEIGHT) {
        LOG_ERR("Generated XML is %ux%u, display is %ux%u; regenerate matching sources",
                (unsigned int)ZMK_NVP_SVG_WIDTH, (unsigned int)ZMK_NVP_SVG_HEIGHT,
                (unsigned int)capabilities.x_resolution, (unsigned int)capabilities.y_resolution);
        return NULL;
    }

    screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(screen, background_color(), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(screen, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);
    lv_obj_clear_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    zmk_nvp_xml_layout_create(screen);

    for (size_t i = 0; i < ARRAY_SIZE(binding_objects); i++) {
        binding_objects[i] = create_binding_object(&zmk_nvp_svg_bindings[i]);
    }
    return screen;
}

static void format_binding_text(char *buffer, size_t size,
                                const struct zmk_nvp_svg_binding *binding,
                                struct field_value value) {
    char value_buffer[20];
    if (!value.valid) {
        snprintf(value_buffer, sizeof(value_buffer), "--");
    } else if (strcmp(binding->format, "output-label") == 0 && value.is_text) {
        snprintf(value_buffer, sizeof(value_buffer), "%s",
                 strcmp(value.text, "none") == 0 ? "--" : value.text);
        if (strcmp(value.text, "usb") == 0) {
            snprintf(value_buffer, sizeof(value_buffer), "USB");
        } else if (strcmp(value.text, "ble") == 0) {
            snprintf(value_buffer, sizeof(value_buffer), "BLE");
        }
    } else if (strcmp(binding->format, "profile-number") == 0 && !value.is_text) {
        snprintf(value_buffer, sizeof(value_buffer), "%s", value.number >= 0 ? "" : "-");
        if (value.number >= 0) {
            snprintf(value_buffer, sizeof(value_buffer), "%ld", (long)value.number + 1);
        }
    } else if (value.is_text) {
        snprintf(value_buffer, sizeof(value_buffer), "%s", value.text);
    } else if (binding->renderer == ZMK_NVP_SVG_RENDER_PERCENT ||
               strcmp(binding->format, "percent") == 0) {
        snprintf(value_buffer, sizeof(value_buffer), "%ld%%", (long)value.number);
    } else {
        snprintf(value_buffer, sizeof(value_buffer), "%ld", (long)value.number);
    }
    snprintf(buffer, size, "%s%s%s", binding->prefix, value_buffer, binding->suffix);
}

void zmk_nvp_xml_screen_update(const struct zmk_nvp_screen_state *state) {
    if (!screen || !state) {
        return;
    }
    for (size_t i = 0; i < ARRAY_SIZE(binding_objects); i++) {
        lv_obj_t *object = binding_objects[i];
        const struct zmk_nvp_svg_binding *binding = &zmk_nvp_svg_bindings[i];
        if (!object) {
            continue;
        }
        struct field_value value = read_field(binding->field_id, state);
        if (binding->renderer == ZMK_NVP_SVG_RENDER_VISIBLE) {
            if (field_matches(value, binding)) {
                lv_obj_clear_flag(object, LV_OBJ_FLAG_HIDDEN);
                zmk_nvp_xml_animation_set_paused(object, false);
            } else {
                lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
                zmk_nvp_xml_animation_set_paused(object, true);
            }
        } else if (binding->renderer == ZMK_NVP_SVG_RENDER_RING) {
            if (!value.valid || value.is_text || value.number <= 0) {
                lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
                continue;
            }
            lv_arc_set_value(object, CLAMP(value.number, 0, 100));
            lv_obj_clear_flag(object, LV_OBJ_FLAG_HIDDEN);
        } else if (binding->renderer == ZMK_NVP_SVG_RENDER_BAR) {
            if (!value.valid || value.is_text) {
                lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
                continue;
            }
            lv_coord_t width = (lv_coord_t)(binding->width * CLAMP(value.number, 0, 100) / 100);
            lv_obj_set_width(object, width);
            if (width == 0) {
                lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
            } else {
                lv_obj_clear_flag(object, LV_OBJ_FLAG_HIDDEN);
            }
        } else {
            char text[48];
            format_binding_text(text, sizeof(text), binding, value);
            lv_label_set_text(object, text);
        }
    }
}

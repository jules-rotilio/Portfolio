//! Colors, from the mock-ups: a dark slate ground and one accent color.

use crate::config::{Appearance, Theme};
use eframe::egui::{self, Color32, CornerRadius, Stroke, Visuals};

/// The colors the window code uses directly (egui's own widgets get theirs
/// from `apply`).
#[derive(Clone, Copy)]
pub struct Palette {
    pub dark: bool,
    pub ground: Color32,
    pub bar: Color32,
    pub panel: Color32,
    pub raised: Color32,
    pub border: Color32,
    pub text: Color32,
    pub muted: Color32,
    pub accent: Color32,
    /// Text on an accent-colored background.
    pub on_accent: Color32,
    pub good: Color32,
    pub warn: Color32,
    pub warn_bg: Color32,
    pub bad: Color32,
    pub meter: Color32,
}

impl Palette {
    pub fn new(appearance: &Appearance, system_dark: bool) -> Palette {
        let dark = match appearance.theme {
            Theme::Dark => true,
            Theme::Light => false,
            Theme::System => system_dark,
        };
        let [r, g, b] = appearance.accent.rgb();
        let accent = Color32::from_rgb(r, g, b);
        // Dark text on light accents, white on dark ones (perceived brightness).
        let bright = 0.299 * r as f32 + 0.587 * g as f32 + 0.114 * b as f32;
        let on_accent = if bright > 140.0 {
            Color32::from_rgb(0x1A, 0x13, 0x00)
        } else {
            Color32::WHITE
        };
        if dark {
            Palette {
                dark,
                ground: Color32::from_rgb(0x12, 0x14, 0x18),
                bar: Color32::from_rgb(0x0D, 0x0F, 0x12),
                panel: Color32::from_rgb(0x1B, 0x1E, 0x24),
                raised: Color32::from_rgb(0x22, 0x26, 0x2E),
                border: Color32::from_rgb(0x2E, 0x33, 0x3C),
                text: Color32::from_rgb(0xEC, 0xEE, 0xF2),
                muted: Color32::from_rgb(0xA3, 0xAA, 0xB6),
                accent,
                on_accent,
                good: Color32::from_rgb(0xB9, 0xE4, 0xC6),
                warn: Color32::from_rgb(0xFF, 0xD5, 0x8A),
                warn_bg: Color32::from_rgb(0x2B, 0x21, 0x11),
                bad: Color32::from_rgb(0xFF, 0xB4, 0xA8),
                meter: Color32::from_rgb(0x5A, 0xA9, 0xF8),
            }
        } else {
            Palette {
                dark,
                ground: Color32::from_rgb(0xF3, 0xF4, 0xF6),
                bar: Color32::from_rgb(0xE6, 0xE8, 0xEC),
                panel: Color32::WHITE,
                raised: Color32::from_rgb(0xEE, 0xF0, 0xF3),
                border: Color32::from_rgb(0xCF, 0xD4, 0xDC),
                text: Color32::from_rgb(0x15, 0x18, 0x1E),
                muted: Color32::from_rgb(0x55, 0x5D, 0x6A),
                accent,
                on_accent,
                good: Color32::from_rgb(0x1E, 0x6B, 0x3A),
                warn: Color32::from_rgb(0x7A, 0x4A, 0x00),
                warn_bg: Color32::from_rgb(0xFF, 0xF1, 0xD6),
                bad: Color32::from_rgb(0xA3, 0x2A, 0x1C),
                meter: Color32::from_rgb(0x1E, 0x6F, 0xD0),
            }
        }
    }

    /// Sets egui's own colors (buttons, sliders, text boxes) to match.
    pub fn apply(&self, ctx: &egui::Context) {
        let mut v = if self.dark {
            Visuals::dark()
        } else {
            Visuals::light()
        };
        v.panel_fill = self.ground;
        v.window_fill = self.panel;
        v.extreme_bg_color = self.raised;
        v.faint_bg_color = self.raised;
        v.window_stroke = Stroke::new(1.0, self.border);
        v.override_text_color = Some(self.text);
        v.hyperlink_color = self.accent;
        v.selection.bg_fill = self.accent;
        v.selection.stroke = Stroke::new(1.0, self.on_accent);
        let radius = CornerRadius::same(7);
        for w in [
            &mut v.widgets.noninteractive,
            &mut v.widgets.inactive,
            &mut v.widgets.hovered,
            &mut v.widgets.active,
            &mut v.widgets.open,
        ] {
            w.corner_radius = radius;
        }
        v.widgets.noninteractive.bg_stroke = Stroke::new(1.0, self.border);
        v.widgets.inactive.weak_bg_fill = self.raised;
        v.widgets.inactive.bg_fill = self.raised;
        v.widgets.inactive.bg_stroke = Stroke::new(1.0, self.border);
        v.widgets.hovered.bg_stroke = Stroke::new(1.0, self.accent);
        v.widgets.active.bg_stroke = Stroke::new(1.0, self.accent);
        v.slider_trailing_fill = true;
        ctx.set_visuals(v);
    }
}

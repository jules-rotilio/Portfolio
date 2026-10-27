//! Small building blocks shared by the main window and the Settings window.

use crate::theme::Palette;
use eframe::egui::{self, Color32, CornerRadius, Margin, RichText, Stroke, Ui, Vec2};

/// A rounded box with an uppercase title, like the mock-ups' cards.
pub fn card<R>(ui: &mut Ui, pal: &Palette, title: &str, add: impl FnOnce(&mut Ui) -> R) -> R {
    egui::Frame::new()
        .fill(pal.panel)
        .stroke(Stroke::new(1.0, pal.border))
        .corner_radius(CornerRadius::same(12))
        .inner_margin(Margin::symmetric(16, 14))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            // Left-aligned, never justified (inside `columns`, egui would
            // otherwise stretch the spaces of wrapped text).
            ui.with_layout(egui::Layout::top_down(egui::Align::Min), |ui| {
                if !title.is_empty() {
                    ui.label(heading(pal, title));
                    ui.add_space(4.0);
                }
                add(ui)
            })
            .inner
        })
        .inner
}

/// What a reducible card's closure is asked to draw.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Part {
    /// The rest of the title line: a summary when reduced.
    Title,
    /// Everything under the title, only when not reduced.
    Body,
}

/// A card whose title reduces it to its title line, or opens it again.
/// Returns whether it is reduced after this frame.
pub fn reducible_card(
    ui: &mut Ui,
    pal: &Palette,
    title: &str,
    reduced: bool,
    mut add: impl FnMut(&mut Ui, Part),
) -> bool {
    card(ui, pal, "", |ui| {
        let mut now = reduced;
        ui.horizontal(|ui| {
            // The triangle is drawn: the default fonts have no small arrows.
            let toggle = ui
                .horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 6.0;
                    let (rect, _) = ui.allocate_exact_size(Vec2::splat(8.0), egui::Sense::hover());
                    let points = if reduced {
                        vec![rect.left_top(), rect.right_center(), rect.left_bottom()]
                    } else {
                        vec![rect.left_top(), rect.right_top(), rect.center_bottom()]
                    };
                    ui.painter()
                        .add(egui::Shape::convex_polygon(points, pal.muted, Stroke::NONE));
                    ui.add(egui::Label::new(heading(pal, title)).selectable(false));
                })
                .response
                .interact(egui::Sense::click())
                .on_hover_cursor(egui::CursorIcon::PointingHand)
                .on_hover_text(if reduced { "Show" } else { "Reduce" });
            if toggle.clicked() {
                now = !reduced;
            }
            add(ui, Part::Title);
        });
        if !reduced {
            ui.add_space(4.0);
            add(ui, Part::Body);
        }
        now
    })
}

pub fn heading(pal: &Palette, text: &str) -> RichText {
    RichText::new(text.to_uppercase())
        .size(12.0)
        .strong()
        .color(pal.muted)
}

pub fn muted(pal: &Palette, text: impl Into<String>) -> RichText {
    RichText::new(text).size(12.5).color(pal.muted)
}

/// A key name in a small box, e.g. [F9].
pub fn chip(ui: &mut Ui, pal: &Palette, text: &str) {
    egui::Frame::new()
        .fill(pal.raised)
        .stroke(Stroke::new(1.0, pal.border))
        .corner_radius(CornerRadius::same(5))
        .inner_margin(Margin::symmetric(6, 2))
        .show(ui, |ui| {
            ui.label(RichText::new(text).monospace().size(11.5).color(pal.text));
        });
}

/// A level meter: `peak` is a sample level 0..1, shown on a dB scale (-60..0 dB).
/// `mark`: a tick at that level, in dB.
pub fn meter(
    ui: &mut Ui,
    pal: &Palette,
    label: &str,
    peak: f32,
    color: Color32,
    mark: Option<f32>,
) {
    let db = if peak > 1e-6 {
        20.0 * peak.log10()
    } else {
        -99.0
    };
    let fraction = ((db + 60.0) / 60.0).clamp(0.0, 1.0);
    ui.horizontal(|ui| {
        ui.add_sized([84.0, 16.0], egui::Label::new(muted(pal, label)));
        let width = (ui.available_width() - 60.0).max(40.0);
        let (rect, _) = ui.allocate_exact_size(Vec2::new(width, 10.0), egui::Sense::hover());
        let painter = ui.painter();
        painter.rect_filled(rect, CornerRadius::same(5), pal.raised);
        let mut filled = rect;
        filled.set_width(rect.width() * fraction);
        painter.rect_filled(filled, CornerRadius::same(5), color);
        if let Some(mark) = mark {
            let x = rect.left() + rect.width() * ((mark + 60.0) / 60.0).clamp(0.0, 1.0);
            painter.line_segment(
                [
                    egui::pos2(x, rect.top() - 2.0),
                    egui::pos2(x, rect.bottom() + 2.0),
                ],
                Stroke::new(2.0, pal.text),
            );
        }
        let text = if db > -99.0 {
            format!("{db:.0} dB")
        } else {
            "—".into()
        };
        ui.label(RichText::new(text).monospace().size(11.5).color(pal.muted));
    });
}

/// A drop-down to pick a device by name. `None` is shown as `none_label`;
/// without one, `None` can't be picked.
pub fn device_combo(
    ui: &mut Ui,
    id: &str,
    value: &mut Option<String>,
    none_label: Option<&str>,
    names: &[String],
) {
    let selected = value
        .clone()
        .unwrap_or_else(|| none_label.unwrap_or("none found").to_string());
    egui::ComboBox::from_id_salt(id)
        .width(ui.available_width().min(380.0))
        .selected_text(selected)
        .show_ui(ui, |ui| {
            if let Some(none_label) = none_label {
                ui.selectable_value(value, None, none_label);
            }
            for name in names {
                ui.selectable_value(value, Some(name.clone()), name);
            }
            // A saved device that isn't plugged in now stays selectable.
            if let Some(current) = value.clone()
                && !names.contains(&current)
            {
                ui.selectable_value(
                    value,
                    Some(current.clone()),
                    format!("{current} (not found)"),
                );
            }
        });
}

/// A filled accent button (Save, ON...).
pub fn accent_button(pal: &Palette, text: impl Into<String>) -> egui::Button<'static> {
    egui::Button::new(RichText::new(text.into()).strong().color(pal.on_accent))
        .fill(pal.accent)
        .stroke(Stroke::new(1.0, pal.accent))
}

/// A colored one-line message with a dot in front.
pub fn status_line(ui: &mut Ui, color: Color32, text: impl Into<String>) {
    ui.horizontal_wrapped(|ui| {
        ui.label(RichText::new("●").color(color));
        ui.label(RichText::new(text).color(color));
    });
}

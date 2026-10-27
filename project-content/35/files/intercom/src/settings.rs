//! The Settings window (its own OS window) and the "edit a key" dialog.

use crate::app::{App, Binding, Tab, effect_summary, typed_key};
use crate::config::{
    Accent, ClickMode, EffectChoice, MouseButton, Page, Sound, Theme, import_audio_config,
    import_valkyrie, valkyrie_config,
};
use crate::hotkeys;
use crate::keys::Key;
use crate::mouse;
use crate::ui_kit::{accent_button, card, chip, device_combo, muted, status_line};
use crate::virtual_mic;
use eframe::egui::{self, Color32, CornerRadius, Margin, RichText, Sense, Stroke, Vec2};

pub fn viewport_id() -> egui::ViewportId {
    egui::ViewportId::from_hash_of("settings")
}

pub fn show(app: &mut App, ctx: &egui::Context) {
    let builder = egui::ViewportBuilder::default()
        .with_title("Intercom · Settings")
        .with_inner_size([980.0, 740.0])
        .with_min_inner_size([760.0, 520.0]);
    ctx.show_viewport_immediate(viewport_id(), builder, |ui, _| {
        if ui.ctx().input(|i| i.viewport().close_requested()) {
            app.settings_open = false;
        }
        // Keys typed here arrive in this window, not the main one.
        if app.capture.is_some()
            && app.reads_window_keys()
            && let Some(key) = typed_key(ui.ctx())
        {
            app.finish_capture(key);
        }
        let pal = app.pal;
        egui::Panel::bottom("settings bar")
            .frame(egui::Frame::NONE)
            .show(ui, |ui| app.bottom_bar(ui, false));
        egui::Panel::left("settings nav")
            .resizable(false)
            .exact_size(200.0)
            .frame(
                egui::Frame::new()
                    .fill(pal.bar)
                    .inner_margin(Margin::same(10)),
            )
            .show(ui, |ui| {
                ui.spacing_mut().item_spacing.y = 4.0;
                for (tab, name) in [
                    (Tab::Audio, "Audio"),
                    (Tab::Voice, "Voice changer"),
                    (Tab::Sounds, "Sounds"),
                    (Tab::Hotkeys, "Hotkeys"),
                    (Tab::Input, "Auto-click & drift"),
                    (Tab::General, "General"),
                ] {
                    let text = RichText::new(name).size(14.0);
                    let button = egui::Button::selectable(app.tab == tab, text)
                        .min_size(Vec2::new(ui.available_width(), 36.0));
                    if ui.add(button).clicked() {
                        app.tab = tab;
                    }
                }
            });
        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(pal.ground)
                    .inner_margin(Margin::same(18)),
            )
            .show(ui, |ui| {
                egui::ScrollArea::vertical()
                    .auto_shrink(false)
                    .show(ui, |ui| {
                        ui.spacing_mut().item_spacing.y = 10.0;
                        match app.tab {
                            Tab::Audio => audio_tab(app, ui),
                            Tab::Voice => voice_tab(app, ui),
                            Tab::Sounds => sounds_tab(app, ui),
                            Tab::Hotkeys => hotkeys_tab(app, ui),
                            Tab::Input => input_tab(app, ui),
                            Tab::General => general_tab(app, ui),
                        }
                    });
            });
        if app.edit.as_ref().is_some_and(|e| e.in_settings) {
            edit_dialog(app, ui.ctx());
        }
    });
}

fn audio_tab(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    let (inputs, outputs) = app.devices.clone();
    let virtual_name = app.vmic.status.output_name().unwrap_or("none found");
    ui.columns(2, |cols| {
        card(&mut cols[0], &pal, "Voice changer", |ui| {
            ui.label(muted(&pal, "Physical input (your mic)"));
            // No "system default": it can be the virtual mic, a loop.
            device_combo(ui, "mic", &mut app.config.audio.mic, None, &inputs);
            ui.label(muted(&pal, "Virtual mics and speaker monitors aren't listed: they would send what others hear back to them."));
            ui.label(muted(&pal, "Virtual output (others hear this)"));
            let auto = format!("Automatic ({virtual_name})");
            device_combo(ui, "voice out", &mut app.config.audio.voice_out, Some(&auto), &outputs);
        });
        cols[0].add_space(10.0);
        gate_card(app, &mut cols[0]);
        cols[0].add_space(10.0);
        card(&mut cols[0], &pal, "Soundboard", |ui| {
            ui.label(muted(&pal, "Virtual output (others hear this)"));
            device_combo(ui, "sound out", &mut app.config.audio.sound_out, Some("Same as the voice changer"), &outputs);
            ui.label(muted(&pal, "Same device as the voice changer: your voice and the sounds are mixed into one stream. A program captured from “Now playing” goes here too."));
        });
        cols[0].add_space(10.0);
        card(&mut cols[0], &pal, "Latency", |ui| {
            ui.horizontal(|ui| {
                ui.label(muted(&pal, "Audio block"));
                let block = egui::Slider::new(&mut app.config.audio.block_ms, 3..=50).suffix(" ms");
                ui.add(block);
            });
            ui.label(muted(&pal, "Smaller: less delay. Larger: fewer cracks, if your computer or Bluetooth headset struggles. The sound restarts when you change it."));
        });
        card(&mut cols[1], &pal, "Headset (what you hear)", |ui| {
            let a = &mut app.config.audio;
            ui.label(muted(&pal, "Device for sounds and the voice test"));
            device_combo(ui, "headset", &mut a.headset, Some("System default"), &outputs);
            ui.horizontal(|ui| {
                ui.label(muted(&pal, "Volume"));
                let mut percent = (a.headset_volume * 100.0).round();
                if ui.add(egui::Slider::new(&mut percent, 0.0..=100.0).suffix(" %")).changed() {
                    a.headset_volume = percent / 100.0;
                }
            });
            ui.checkbox(&mut a.separate_test_device, "Use a different device for the voice test");
            ui.add_enabled_ui(a.separate_test_device, |ui| {
                ui.label(muted(&pal, "Voice test device"));
                device_combo(ui, "test", &mut a.test_device, Some("System default"), &outputs);
            });
            ui.label(muted(&pal, "Bluetooth adds 100 ms or more to what you hear. Others are not affected."));
        });
        cols[1].add_space(10.0);
        virtual_card(app, &mut cols[1]);
        if app.discord {
            cols[1].add_space(10.0);
            discord_card(app, &mut cols[1]);
        }
    });
}

/// The noise gate: on or off, how far above the noise it opens, and the
/// floor it measured.
fn gate_card(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    let floor = app.shared.noise_floor();
    card(ui, &pal, "Noise gate", |ui| {
        let a = &mut app.config.audio;
        ui.checkbox(&mut a.noise_gate, "Silence the mic between words");
        ui.add_enabled_ui(a.noise_gate, |ui| {
            ui.horizontal(|ui| {
                ui.label(muted(&pal, "Opens at"));
                let slider = egui::Slider::new(&mut a.gate_margin_db, 3.0..=24.0)
                    .step_by(1.0)
                    .suffix(" dB above the noise");
                ui.add(slider);
            });
        });
        match floor {
            Some(floor) if a.noise_gate => status_line(
                ui,
                pal.good,
                format!(
                    "Noise floor {floor:.0} dB · opens above {:.0} dB (the mark on the mic meter)",
                    floor + a.gate_margin_db
                ),
            ),
            Some(floor) => status_line(ui, pal.muted, format!("Noise floor {floor:.0} dB")),
            None => status_line(ui, pal.muted, "Measuring the noise floor…"),
        }
        ui.label(muted(&pal, "The noise floor is measured all the time, from the pauses between your sentences: nothing to set up, and a new mic is measured again by itself. If the ends of words are cut, lower “Opens at”; if noise still gets through, raise it."));
    });
}

/// Discord's own processing fights music and sound effects.
fn discord_card(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    let mic = if cfg!(windows) {
        "CABLE Output"
    } else {
        app.config.audio.virtual_mic.name.as_str()
    };
    card(ui, &pal, "Discord", |ui| {
        ui.label(muted(&pal, "Discord is installed. For your sounds and program audio to reach your friends clean, in Discord › User Settings › Voice & Video:"));
        for tip in [
            format!("Input device: “{mic}”"),
            "Noise suppression: None (Krisp cuts music and sound effects)".to_string(),
            "Echo cancellation and Automatic gain control: off".to_string(),
            "Input sensitivity: “Automatically determine” off, slider all the way left (Intercom's noise gate already does this)".to_string(),
        ] {
            ui.label(format!("•  {tip}"));
        }
        ui.label(muted(&pal, "Discord is never offered in “Capture program audio”: your friends would hear themselves."));
    });
}

fn virtual_card(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    if cfg!(windows) {
        card(ui, &pal, "Virtual cable · Windows", |ui| {
            match app.vmic.status {
                virtual_mic::Status::CableFound => {
                    status_line(ui, pal.good, "VB-Audio Virtual Cable found")
                }
                _ => {
                    status_line(ui, pal.warn, "VB-Audio Virtual Cable not found");
                    ui.hyperlink_to(
                        "Download VB-Audio Virtual Cable",
                        "https://vb-audio.com/Cable/",
                    );
                }
            }
            ui.label(muted(
                &pal,
                "Intercom plays into “CABLE Input”. Pick “CABLE Output” as the mic in your game.",
            ));
            ui.label(muted(
                &pal,
                "Windows can't create a virtual mic by itself, so Intercom uses this one.",
            ));
            default_mic_option(app, ui, "Make “CABLE Output” the default microphone");
            ui.horizontal(|ui| {
                if ui.button("Open Windows sound settings").clicked() {
                    let _ = std::process::Command::new("cmd")
                        .args(["/C", "start", "ms-settings:sound"])
                        .spawn();
                }
                if ui.button("Refresh device lists").clicked() {
                    app.refresh_devices();
                }
            });
        });
        return;
    }
    card(ui, &pal, "Virtual microphone · Linux", |ui| {
        let vm = &mut app.config.audio.virtual_mic;
        ui.label(muted(&pal, "Name shown in Discord and games"));
        ui.add(
            egui::TextEdit::singleline(&mut vm.name).desired_width(ui.available_width().min(380.0)),
        );
        ui.checkbox(&mut vm.create_on_start, "Create it when Intercom starts");
        ui.checkbox(&mut vm.keep_after_close, "Keep it after closing");
        match &app.vmic.status {
            virtual_mic::Status::Ready { modules, created } => {
                let ids: Vec<String> = modules.iter().map(u32::to_string).collect();
                status_line(ui, pal.good, format!("Ready (modules {})", ids.join(", ")));
                ui.label(muted(
                    &pal,
                    match (created, vm.keep_after_close) {
                        (_, true) => "Kept after Intercom closes",
                        (true, false) => "Created by Intercom, removed when it closes",
                        (false, false) => "Found from last time, removed when Intercom closes",
                    },
                ));
            }
            virtual_mic::Status::Failed(e) => status_line(ui, pal.bad, e),
            _ => status_line(ui, pal.muted, "Not created"),
        }
        default_mic_option(app, ui, "Make it the system's default microphone");
        if ui.button("Refresh device lists").clicked() {
            app.refresh_devices();
        }
    });
}

/// "Make the virtual mic the default", with what it does, and what went wrong.
fn default_mic_option(app: &mut App, ui: &mut egui::Ui, label: &str) {
    let pal = app.pal;
    ui.checkbox(&mut app.config.audio.virtual_mic_default, label);
    ui.label(muted(&pal, "Games and websites that use the default mic then hear Intercom without being set up. Your own mic is the default again when Intercom closes or when you untick this."));
    if let Some(problem) = &app.default_mic_problem {
        status_line(ui, pal.warn, problem);
    }
}

fn voice_tab(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    card(ui, &pal, "Effect", |ui| {
        ui.label(muted(&pal, "Changes apply live, between two audio blocks"));
        ui.columns(5, |cols| {
            for (col, choice) in cols.iter_mut().zip(EffectChoice::ALL) {
                let selected = app.config.voice.effect == choice;
                let frame = egui::Frame::new()
                    .fill(if selected {
                        pal.accent.gamma_multiply(0.18)
                    } else {
                        pal.raised
                    })
                    .stroke(Stroke::new(
                        if selected { 2.0 } else { 1.0 },
                        if selected { pal.accent } else { pal.border },
                    ))
                    .corner_radius(CornerRadius::same(10))
                    .inner_margin(Margin::same(12));
                let response = frame
                    .show(col, |ui| {
                        ui.set_width(ui.available_width());
                        ui.with_layout(egui::Layout::top_down(egui::Align::Min), |ui| {
                            ui.label(RichText::new(choice.label()).strong().size(15.0));
                            ui.label(muted(&pal, choice.description()));
                        });
                    })
                    .response
                    .interact(Sense::click());
                if response.clicked() {
                    app.config.voice.effect = choice;
                }
            }
        });
    });
    ui.columns(2, |cols| {
        let v = &mut app.config.voice;
        card(&mut cols[0], &pal, &format!("{} options", v.effect.label()), |ui| match v.effect {
            EffectChoice::Pitch => {
                ui.label(muted(&pal, "Change in semitones (+12 = one octave up)"));
                ui.add(egui::Slider::new(&mut v.pitch, -12.0..=12.0).step_by(0.5).suffix(" st"));
                ui.label(muted(&pal, "Window: smaller = less delay, larger = smoother"));
                ui.add(egui::Slider::new(&mut v.window_ms, 10.0..=60.0).step_by(1.0).suffix(" ms"));
            }
            EffectChoice::Robot => {
                ui.label(muted(&pal, "Note"));
                ui.add(egui::Slider::new(&mut v.freq, 40.0..=1000.0).logarithmic(true).suffix(" Hz"));
                ui.label(muted(&pal, "Lower notes are deeper and a little slower to respond. Try 150 to 200 Hz if words get mumbly."));
            }
            _ => {
                let mut bits = v.bits.unwrap_or(16);
                ui.label(muted(&pal, "Bits per sample: fewer = grittier (4: 8-bit era, 8: 16-bit era)"));
                if ui.add(egui::Slider::new(&mut bits, 1..=16)).changed() {
                    v.bits = Some(bits);
                }
                let preset_rate = match v.effect {
                    EffectChoice::FourBit => 4000,
                    EffectChoice::EightBit => 8000,
                    _ => 12_000,
                };
                let mut rate = v.rate.unwrap_or(preset_rate);
                ui.label(muted(&pal, "Console's sample rate: lower = duller, more whistles"));
                if ui.add(egui::Slider::new(&mut rate, 1000..=48_000).logarithmic(true).suffix(" Hz")).changed() {
                    v.rate = Some(rate);
                }
                if (v.bits.is_some() || v.rate.is_some()) && ui.button("Back to the preset").clicked() {
                    v.bits = None;
                    v.rate = None;
                }
            }
        });
        card(&mut cols[1], &pal, "Behaviour", |ui| {
            ui.horizontal(|ui| {
                ui.label("Voice changer on/off key");
                chip(ui, &pal, app.config.hotkeys.voice_toggle.label());
            });
            ui.checkbox(&mut app.config.voice.on_at_start, "Turn ON when Intercom starts");
            ui.checkbox(&mut app.test_on, "Test: hear my voice in the headset");
            let args = app.config.voice.effect_args();
            let delay = app.engine.effect_delay_ms(&args);
            ui.label(muted(&pal, format!(
                "{} · effect delay {}",
                effect_summary(&app.config.voice),
                delay.map(|d| format!("{d:.1} ms")).unwrap_or_else(|| "—".into())
            )));
            let underruns = app.shared.underruns.load(std::sync::atomic::Ordering::Relaxed);
            ui.label(muted(&pal, format!("Clicks (underruns) so far: {underruns}")));
        });
    });
    announce_card(app, ui);
    card(ui, &pal, "When OFF", |ui| {
        ui.label(muted(&pal, "Nothing from your mic reaches the virtual output. The mic stays open, so turning the voice changer back ON is instant. The test still works, so you can try effects without anyone hearing. Numpad sounds play either way."));
    });
}

fn sounds_tab(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    app.settings_page = app
        .settings_page
        .min(app.config.pages.len().saturating_sub(1));
    ui.horizontal_top(|ui| {
        ui.spacing_mut().item_spacing.x = 14.0;
        {
            ui.vertical(|ui| {
                ui.set_width(250.0);
                card(ui, &pal, "Pages", |ui| {
                    let count = app.config.pages.len();
                    let mut action = None;
                    for i in 0..count {
                        ui.horizontal(|ui| {
                            let selected = app.settings_page == i;
                            let name = format!("{}  {}", i + 1, app.config.pages[i].name);
                            if ui
                                .add(
                                    egui::Button::selectable(selected, name)
                                        .min_size(Vec2::new(140.0, 28.0)),
                                )
                                .clicked()
                            {
                                app.settings_page = i;
                            }
                            if ui
                                .add_enabled(i > 0, egui::Button::new("↑").small())
                                .on_hover_text("Move up")
                                .clicked()
                            {
                                action = Some(("up", i));
                            }
                            if ui
                                .add_enabled(i + 1 < count, egui::Button::new("↓").small())
                                .on_hover_text("Move down")
                                .clicked()
                            {
                                action = Some(("down", i));
                            }
                            if ui
                                .add_enabled(count > 1, egui::Button::new("🗑").small())
                                .on_hover_text("Delete page")
                                .clicked()
                            {
                                action = Some(("delete", i));
                            }
                        });
                    }
                    match action {
                        Some(("up", i)) => {
                            app.config.pages.swap(i, i - 1);
                            app.settings_page = i - 1;
                        }
                        Some(("down", i)) => {
                            app.config.pages.swap(i, i + 1);
                            app.settings_page = i + 1;
                        }
                        Some((_, i)) => {
                            app.config.pages.remove(i);
                        }
                        None => {}
                    }
                    if ui.button("+ New page").clicked() {
                        let n = app.config.pages.len() + 1;
                        app.config.pages.push(Page {
                            name: format!("Page {n}"),
                            ..Page::default()
                        });
                        app.settings_page = n - 1;
                    }
                    if ui.button("Import AudioConfig.json…").clicked()
                        && let Some(path) = rfd::FileDialog::new()
                            .add_filter("AudioConfig", &["json"])
                            .pick_file()
                    {
                        match std::fs::read_to_string(&path)
                            .map_err(|e| e.to_string())
                            .and_then(|t| import_audio_config(&t))
                        {
                            Ok(pages) => {
                                let n = pages.len();
                                app.config.pages.extend(pages);
                                app.message = Some((
                                    format!("Imported {n} page(s) from {}", path.display()),
                                    false,
                                ));
                            }
                            Err(e) => app.message = Some((format!("Import failed: {e}"), true)),
                        }
                    }
                    ui.label(muted(
                        &pal,
                        "Import turns the old app's pages “0”, “1”… into pages here.",
                    ));
                });
            });
            ui.vertical(|ui| {
                // Only the width left, so the list never runs off the window.
                ui.set_width(ui.available_width());
                let page = app.settings_page;
                card(ui, &pal, "Keys of this page", |ui| {
                    let Some(p) = app.config.pages.get_mut(page) else {
                        return;
                    };
                    ui.horizontal(|ui| {
                        ui.label(muted(&pal, "Name"));
                        ui.text_edit_singleline(&mut p.name);
                    });
                    ui.label(muted(
                        &pal,
                        format!(
                            "{} always stops the sound",
                            app.config.hotkeys.stop_sound.label()
                        ),
                    ));
                    let mut edit = None;
                    // One row per key: chip, button kept on the right, then the
                    // name cut with "…" in the space left, so nothing runs off.
                    for key in Key::SOUND_KEYS {
                        ui.horizontal(|ui| {
                            ui.add_sized([52.0, 22.0], |ui: &mut egui::Ui| {
                                ui.horizontal(|ui| chip(ui, &pal, key.label())).response
                            });
                            let sound = p.keys.get(&key).filter(|s| !s.files.is_empty());
                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    let button = if sound.is_some() {
                                        "Edit…"
                                    } else {
                                        "Assign…"
                                    };
                                    if ui.button(button).clicked() {
                                        edit = Some(key);
                                    }
                                    ui.with_layout(
                                        egui::Layout::left_to_right(egui::Align::Center),
                                        |ui| match sound {
                                            Some(sound) => {
                                                let more = sound.files.len() - 1;
                                                let missing =
                                                    sound.files.iter().any(|f| !f.exists());
                                                let mut text = RichText::new(if more > 0 {
                                                    format!("{} + {more} random", sound.title())
                                                } else {
                                                    sound.title()
                                                });
                                                if missing {
                                                    text = text.color(pal.bad);
                                                }
                                                let label =
                                                    ui.add(egui::Label::new(text).truncate());
                                                if missing {
                                                    label.on_hover_text(
                                                        "A file is missing on this computer",
                                                    );
                                                }
                                            }
                                            None => {
                                                ui.label(muted(&pal, "Empty"));
                                            }
                                        },
                                    );
                                },
                            );
                        });
                    }
                    if let Some(key) = edit {
                        app.open_edit(page, key, true);
                    }
                });
            });
        }
    });
}

/// One row of the Hotkeys tab: name, key(s), "Change" buttons.
fn key_row(app: &mut App, ui: &mut egui::Ui, name: &str, keys: &[(Binding, Option<Key>)]) {
    let pal = app.pal;
    let conflicts = app.config.conflicts();
    ui.label(name);
    ui.horizontal(|ui| {
        for &(binding, key) in keys {
            let waiting = app.capture.as_ref().is_some_and(|(b, _)| *b == binding);
            if waiting {
                ui.label(RichText::new("Press a key… (Esc cancels)").color(pal.warn));
                if ui.button("Cancel").clicked() {
                    app.cancel_capture();
                }
            } else {
                let text = key.map(|k| k.label()).unwrap_or("—");
                let clash = key.is_some_and(|k| conflicts.iter().any(|(c, _)| *c == k));
                let text = RichText::new(text).monospace();
                let text = if clash { text.color(pal.bad) } else { text };
                if ui
                    .button(text)
                    .on_hover_text("Click, then press the new key")
                    .clicked()
                {
                    app.start_capture(binding);
                }
            }
        }
    });
    ui.end_row();
}

fn hotkeys_tab(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    let h = app.config.hotkeys.clone();
    card(ui, &pal, "Global keys · work while you play", |ui| {
        ui.label(muted(&pal, "Click a key, then press the new one."));
        egui::Grid::new("hotkeys")
            .num_columns(2)
            .spacing([24.0, 8.0])
            .show(ui, |ui| {
                key_row(
                    app,
                    ui,
                    "Voice changer on / off",
                    &[(Binding::VoiceToggle, Some(h.voice_toggle))],
                );
                key_row(
                    app,
                    ui,
                    "Soundboard volume up / down",
                    &[
                        (Binding::VolumeUp, Some(h.volume_up)),
                        (Binding::VolumeDown, Some(h.volume_down)),
                    ],
                );
                ui.label("Volume step");
                ui.add(
                    egui::DragValue::new(&mut app.config.hotkeys.volume_step)
                        .range(1..=50)
                        .suffix(" %"),
                );
                ui.end_row();
                key_row(
                    app,
                    ui,
                    "Next page / previous page",
                    &[
                        (Binding::PageNext, Some(h.page_next)),
                        (Binding::PagePrev, Some(h.page_prev)),
                    ],
                );
                key_row(
                    app,
                    ui,
                    "Stop sound",
                    &[(Binding::StopSound, Some(h.stop_sound))],
                );
                key_row(
                    app,
                    ui,
                    "Mouse drift left / right",
                    &[
                        (Binding::DriftLeft, Some(h.drift_left)),
                        (Binding::DriftRight, Some(h.drift_right)),
                    ],
                );
                key_row(
                    app,
                    ui,
                    "Auto-click trigger",
                    &[(Binding::ClickTrigger, Some(app.config.autoclick.trigger))],
                );
            });
        for (key, uses) in app.config.conflicts() {
            status_line(
                ui,
                pal.bad,
                format!(
                    "{} is used for: {}. Pick another key before saving.",
                    key.label(),
                    uses.join(", ")
                ),
            );
        }
    });
    card(ui, &pal, "Sound keys", |ui| {
        ui.label(muted(&pal, "Numpad 0 to 9, / * - + and Enter play the current page's sounds. Assign them in the Sounds tab. Keys still reach the game: Intercom only listens, so a frozen app can never block your keyboard."));
        if !app.hotkeys.is_running() || app.hotkeys.needs_permission() {
            status_line(
                ui,
                pal.warn,
                "Global keys can't read every keyboard (see General). “Change” also hears keys pressed in this window.",
            );
        }
    });
}

fn input_tab(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    mouse_status(app, ui);
    let a = app.config.autoclick.clone();
    ui.columns(2, |cols| {
        card(&mut cols[0], &pal, "Auto-click", |ui| {
            {
                let c = &mut app.config.autoclick;
                ui.checkbox(&mut c.enabled, "Enabled");
                egui::Grid::new("click").num_columns(2).spacing([16.0, 8.0]).show(ui, |ui| {
                    ui.label("Mouse button");
                    egui::ComboBox::from_id_salt("button")
                        .selected_text(format!("{:?}", c.button))
                        .show_ui(ui, |ui| {
                            for b in [MouseButton::Left, MouseButton::Right, MouseButton::Middle] {
                                ui.selectable_value(&mut c.button, b, format!("{b:?}"));
                            }
                        });
                    ui.end_row();
                    ui.label("Mode");
                    ui.horizontal(|ui| {
                        ui.selectable_value(&mut c.mode, ClickMode::Toggle, "Toggle");
                        ui.selectable_value(&mut c.mode, ClickMode::Hold, "Hold");
                    });
                    ui.end_row();
                    ui.label("Rate");
                    let max = c.max_rate.max(1.0);
                    let rate = egui::Slider::new(&mut c.rate, 1.0..=max)
                        .step_by(1.0)
                        .max_decimals(0)
                        .suffix(" clicks/s");
                    ui.add(rate);
                    ui.end_row();
                    ui.label("Highest rate");
                    ui.add(egui::DragValue::new(&mut c.max_rate).range(1.0..=100.0).max_decimals(0).suffix(" /s"));
                    ui.end_row();
                    ui.label("Press length");
                    ui.horizontal(|ui| {
                        let mut auto = c.press_ms.is_none();
                        if ui.checkbox(&mut auto, "auto").changed() {
                            c.press_ms = if auto { None } else { Some(10.0) };
                        }
                        if let Some(ms) = &mut c.press_ms {
                            ui.add(egui::DragValue::new(ms).range(1.0..=500.0).suffix(" ms"));
                        }
                    });
                    ui.end_row();
                    ui.checkbox(&mut c.sounds, "Start / stop sounds");
                    let mut percent = (c.sound_volume * 100.0).round();
                    if ui.add(egui::Slider::new(&mut percent, 0.0..=100.0).suffix(" %")).changed() {
                        c.sound_volume = percent / 100.0;
                    }
                    ui.end_row();
                });
                c.rate = c.rate.min(c.max_rate);
            }
            egui::Grid::new("click keys").num_columns(2).spacing([16.0, 8.0]).show(ui, |ui| {
                key_row(app, ui, "Trigger key", &[(Binding::ClickTrigger, Some(a.trigger))]);
                key_row(app, ui, "Faster / slower / mode", &[
                    (Binding::ClickFaster, a.faster_key),
                    (Binding::ClickSlower, a.slower_key),
                    (Binding::ClickMode, a.mode_key),
                ]);
            });
            if (a.faster_key.is_some() || a.slower_key.is_some() || a.mode_key.is_some())
                && ui.button("Clear the optional keys").clicked()
            {
                app.config.autoclick.faster_key = None;
                app.config.autoclick.slower_key = None;
                app.config.autoclick.mode_key = None;
            }
            ui.label(muted(&pal, "Toggle: one press starts, the next stops. Hold: clicks while the key is down. The faster / slower / mode keys change the settings above (Save keeps them)."));
            if let Some(path) = valkyrie_config()
                && ui
                    .button("Import from Valkyrie")
                    .on_hover_text(path.display().to_string())
                    .clicked()
            {
                match std::fs::read_to_string(&path)
                    .map_err(|e| e.to_string())
                    .and_then(|text| import_valkyrie(&text, &app.config.autoclick))
                {
                    Ok(imported) => app.config.autoclick = imported,
                    Err(e) => app.message = Some((format!("Not imported: {e}"), true)),
                }
            }
        });
        card(&mut cols[1], &pal, "Mouse drift", |ui| {
            let d = &mut app.config.drift;
            ui.checkbox(&mut d.enabled, "Enabled");
            ui.horizontal(|ui| {
                ui.label("Move");
                ui.add(egui::DragValue::new(&mut d.px).range(1..=200).suffix(" px"));
                ui.label("every");
                ui.add(egui::DragValue::new(&mut d.every_ms).range(5..=1000).suffix(" ms"));
            });
            let speed = d.px as f32 * 1000.0 / d.every_ms.max(1) as f32;
            ui.label(RichText::new(format!("{speed:.0} px/s")).size(18.0).strong());
            ui.label(muted(&pal, "A key press starts drifting that way; the same key stops it; the other key switches direction. Keys: Hotkeys tab."));
        });
        cols[1].add_space(10.0);
        card(&mut cols[1], &pal, "Clicks and drift stop when", |ui| {
            ui.label(muted(&pal, "You turn the feature off here, or close Intercom. A held mouse button is always released."));
            let live = app.mouse.live();
            if (live.clicking || live.drift.is_some()) && ui.button("Stop now").clicked() {
                app.mouse.stop_all();
            }
            ui.label(RichText::new("Some games' anti-cheat flags simulated clicks. Check the rules before using this online.").color(pal.warn));
        });
    });
}

/// The spoken "Voice changer on/off", heard in the headset only.
fn announce_card(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    let mut try_line = None;
    card(ui, &pal, "Spoken confirmation", |ui| {
        let v = &mut app.config.voice;
        ui.checkbox(
            &mut v.announce,
            "Say “Voice changer on / off” in my headset when it switches",
        );
        ui.add_enabled_ui(v.announce, |ui| {
            ui.horizontal(|ui| {
                ui.label("Volume");
                let mut percent = (v.announce_volume * 100.0).round();
                if ui
                    .add(egui::Slider::new(&mut percent, 0.0..=100.0).suffix(" %"))
                    .changed()
                {
                    v.announce_volume = percent / 100.0;
                }
            });
            ui.checkbox(
                &mut v.announce_in_effect,
                "Speak “on” in the new voice (hear what others will hear)",
            );
            egui::Grid::new("announce lines")
                .num_columns(2)
                .spacing([16.0, 8.0])
                .show(ui, |ui| {
                    for (on, label) in [(true, "“On” line"), (false, "“Off” line")] {
                        ui.label(label);
                        ui.horizontal(|ui| {
                            let file = if on {
                                &mut v.announce_on
                            } else {
                                &mut v.announce_off
                            };
                            let name = file.as_ref().map_or("Built-in voice".into(), |p| {
                                p.file_name().map_or(p.display().to_string(), |n| {
                                    n.to_string_lossy().into_owned()
                                })
                            });
                            ui.label(RichText::new(name).strong());
                            if ui.button("Choose…").clicked()
                                && let Some(path) = pick_audio()
                            {
                                *file = Some(path);
                            }
                            if file.is_some() && ui.button("Built-in").clicked() {
                                *file = None;
                            }
                            if ui.button("▶ Try").clicked() {
                                try_line = Some(on);
                            }
                        });
                        ui.end_row();
                    }
                });
        });
        ui.label(muted(&pal, "Only you hear it, never the game. The built-in lines were made with the Piper text-to-speech engine (voice “joe”, public domain); pick your own file to use another voice."));
    });
    if let Some(on) = try_line {
        let mut voice = app.config.voice.clone();
        voice.announce = true;
        crate::announce::announce(&app.engine.player, &voice, on);
    }
}

/// Whether the virtual mouse works, and what it is doing.
fn mouse_status(app: &App, ui: &mut egui::Ui) {
    let pal = app.pal;
    match &app.mouse.status {
        mouse::Status::Ready => {
            let live = app.mouse.live();
            let mut doing = Vec::new();
            if live.clicking {
                doing.push(format!("clicking at {} /s", live.rate));
            }
            match live.drift {
                Some(mouse::Direction::Left) => doing.push("drifting left".into()),
                Some(mouse::Direction::Right) => doing.push("drifting right".into()),
                None => {}
            }
            if let Some(e) = &live.error {
                status_line(ui, pal.bad, e);
            } else if doing.is_empty() {
                status_line(ui, pal.good, "Ready: press the trigger or a drift key");
            } else {
                status_line(ui, pal.accent, format!("Now {}", doing.join(" and ")));
            }
        }
        mouse::Status::NoPermission => {
            status_line(
                ui,
                pal.warn,
                "Intercom can't create its virtual mouse: /dev/uinput can't be opened. Run this once, then restart Intercom:",
            );
            ui.label(RichText::new(UINPUT_RULE).monospace());
        }
        mouse::Status::Failed(e) => status_line(ui, pal.bad, format!("No virtual mouse: {e}")),
    }
}

/// Lets the logged-in user use /dev/uinput (the rule Steam installs too).
const UINPUT_RULE: &str = "echo 'KERNEL==\"uinput\", SUBSYSTEM==\"misc\", TAG+=\"uaccess\", OPTIONS+=\"static_node=uinput\"' | sudo tee /etc/udev/rules.d/70-intercom-uinput.rules && sudo udevadm control --reload && sudo udevadm trigger";

fn general_tab(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    ui.columns(2, |cols| {
        card(&mut cols[0], &pal, "Only while a program is in front", |ui| {
            let focus = app.controller.focus.lock().unwrap().clone();
            let g = &mut app.config.general;
            ui.checkbox(&mut g.focus_only, "Ignore Intercom's keys in other programs");
            ui.horizontal(|ui| {
                ui.label("Program");
                ui.text_edit_singleline(&mut g.focus_program);
            });
            let front = match &focus.front {
                Some(f) if f.is_us => "Intercom".to_string(),
                Some(f) => f.names.join(" · "),
                None if cfg!(windows) => "nothing".into(),
                None => "a window Intercom can't identify (native Wayland)".into(),
            };
            let colour = if focus.in_front { pal.good } else { pal.muted };
            status_line(ui, colour, format!("In front now: {front}"));
            if let Some(last) = focus.last_other.filter(|l| *l != g.focus_program)
                && ui.button(format!("Use “{last}” (the last program in front)")).clicked()
            {
                g.focus_program = last;
            }
            let how = if cfg!(windows) {
                "Name the program's file, like SCPSL.exe."
            } else {
                "Name the program's file, like SCPSL.x86_64, or SCPSL.exe for a Windows game run with Proton. Linux can only see programs that run through XWayland, which games do."
            };
            ui.label(muted(&pal, format!("{how} When you leave the program, the clicking, the drift and the sound stop.")));
        });
        cols[0].add_space(10.0);
        card(&mut cols[0], &pal, "Settings file", |ui| {
            ui.label(RichText::new(app.config_path.display().to_string()).monospace());
            ui.horizontal(|ui| {
                if ui.button("Open folder").clicked()
                    && let Some(dir) = app.config_path.parent()
                {
                    let _ = std::fs::create_dir_all(dir);
                    let opener = if cfg!(windows) { "explorer" } else { "xdg-open" };
                    let _ = std::process::Command::new(opener).arg(dir).spawn();
                }
                if ui.button("Reload from disk").clicked() {
                    match crate::config::Config::load(&app.config_path) {
                        Ok(Some(config)) => app.config = config,
                        Ok(None) => app.message = Some(("No settings file yet: Save writes one".into(), false)),
                        Err(e) => app.message = Some((e, true)),
                    }
                }
            });
            ui.label(muted(&pal, "Save writes this file. Undo goes back one change at a time."));
        });
        cols[0].add_space(10.0);
        card(&mut cols[0], &pal, "Window", |ui| {
            ui.checkbox(&mut app.config.general.keep_on_top, "Keep the main window on top");
            ui.checkbox(&mut app.config.general.ask_before_close, "Ask before closing with unsaved changes");
            let label = if cfg!(windows) { "Start with Windows" } else { "Start when I log in" };
            ui.checkbox(&mut app.config.general.start_with_windows, label)
                .on_hover_text("Applied when you save");
        });

        appearance_card(app, &mut cols[1]);
        cols[1].add_space(10.0);
        platform_card(app, &mut cols[1]);
    });
}

fn appearance_card(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    card(ui, &pal, "Appearance", |ui| {
        let look = &mut app.config.appearance;
        ui.horizontal(|ui| {
            ui.label("Theme");
            ui.selectable_value(&mut look.theme, Theme::Dark, "Dark");
            ui.selectable_value(&mut look.theme, Theme::Light, "Light");
            ui.selectable_value(&mut look.theme, Theme::System, "System");
        });
        ui.label("Accent color");
        ui.horizontal(|ui| {
            for accent in Accent::SWATCHES {
                let [r, g, b] = accent.rgb();
                let (rect, response) = ui.allocate_exact_size(Vec2::splat(30.0), Sense::click());
                let painter = ui.painter();
                painter.circle_filled(rect.center(), 13.0, Color32::from_rgb(r, g, b));
                if look.accent == accent {
                    painter.circle_stroke(rect.center(), 15.0, Stroke::new(2.0, pal.text));
                }
                if response.on_hover_text(accent.name()).clicked() {
                    look.accent = accent;
                }
            }
            let mut rgb = look.accent.rgb();
            if egui::color_picker::color_edit_button_srgb(ui, &mut rgb).changed() {
                look.accent = Accent::Custom(rgb);
            }
            ui.label(muted(&pal, "Custom"));
        });
        ui.horizontal(|ui| {
            let _ = ui.add(accent_button(&pal, "ON").min_size(Vec2::new(60.0, 30.0)));
            let (rect, _) = ui
                .allocate_exact_size(Vec2::new(ui.available_width() - 70.0, 10.0), Sense::hover());
            ui.painter()
                .rect_filled(rect, CornerRadius::same(5), pal.raised);
            let mut filled = rect;
            filled.set_width(rect.width() * 0.62);
            ui.painter()
                .rect_filled(filled, CornerRadius::same(5), pal.accent);
            ui.label(muted(&pal, "Preview"));
        });
    });
}

fn platform_card(app: &mut App, ui: &mut egui::Ui) {
    let pal = app.pal;
    if cfg!(windows) {
        card(ui, &pal, "Games run as administrator · Windows", |ui| {
            if app.is_admin {
                status_line(ui, pal.good, "Intercom runs as administrator");
            } else {
                status_line(ui, pal.muted, "Intercom runs as a normal user");
            }
            ui.label(muted(&pal, "Windows hides keys from Intercom and blocks its clicks while a game running as administrator is in front. If the hotkeys do nothing in a game, run Intercom as administrator too."));
            if !app.is_admin
                && ui.button("Restart as administrator").clicked()
                && crate::platform::restart_as_admin()
            {
                ui.ctx()
                    .send_viewport_cmd_to(egui::ViewportId::ROOT, egui::ViewportCommand::Close);
            }
            ui.checkbox(
                &mut app.config.general.always_admin,
                "Always start as administrator",
            );
        });
        return;
    }
    card(ui, &pal, "Keyboard access · Linux", |ui| {
        match &app.hotkeys {
            hotkeys::Status::Running { refused: 0 } => {
                status_line(ui, pal.good, "Global keys can read every keyboard")
            }
            hotkeys::Status::Running { refused } => status_line(
                ui,
                pal.warn,
                format!(
                    "Some devices are read, but {refused} can't be: your keyboard may be one of them"
                ),
            ),
            hotkeys::Status::NoPermission => {
                status_line(ui, pal.warn, "Can't read the keyboard yet")
            }
            hotkeys::Status::Failed(e) => status_line(ui, pal.bad, e),
        }
        if app.hotkeys.needs_permission() {
            ui.label(muted(&pal, "Global keys need read access to /dev/input. Run this once, then log out and back in:"));
            ui.label(RichText::new("sudo usermod -aG input $USER").monospace());
        }
        if (!app.hotkeys.is_running() || app.hotkeys.needs_permission())
            && ui.button("Check again").clicked()
        {
            app.retry_hotkeys();
        }
    });
}

/// The "edit a key" dialog: files picked at random, the key's own volume.
pub fn edit_dialog(app: &mut App, ctx: &egui::Context) {
    let pal = app.pal;
    let Some(edit) = &mut app.edit else { return };
    let page_name = app
        .config
        .pages
        .get(edit.page)
        .map(|p| p.name.clone())
        .unwrap_or_default();
    let mut close = false;
    let mut save = false;
    let mut clear = false;
    let mut preview = false;
    egui::Modal::new(egui::Id::unique(("edit", edit.page, edit.key))).show(ctx, |ui| {
        ui.set_width(520.0);
        ui.heading(format!("Numpad {}", edit.key.label()));
        ui.label(muted(&pal, format!("Page “{page_name}”")));
        ui.add_space(8.0);
        ui.label(muted(&pal, "Files · one is picked at random each time"));
        let mut remove = None;
        for (i, file) in edit.draft.files.iter_mut().enumerate() {
            ui.horizontal(|ui| {
                let mut text = file.display().to_string();
                if ui
                    .add(egui::TextEdit::singleline(&mut text).desired_width(330.0))
                    .changed()
                {
                    *file = text.into();
                }
                if ui.button("Browse…").clicked()
                    && let Some(path) = pick_audio()
                {
                    *file = path;
                }
                if ui.button("✕").on_hover_text("Remove").clicked() {
                    remove = Some(i);
                }
            });
        }
        if let Some(i) = remove {
            edit.draft.files.remove(i);
        }
        if ui.button("+ Add a file").clicked()
            && let Some(path) = pick_audio()
        {
            edit.draft.files.push(path);
        }
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            ui.label(muted(&pal, "Volume of this sound"));
            let mut percent = (edit.draft.volume * 100.0).round();
            if ui
                .add(egui::Slider::new(&mut percent, 0.0..=200.0).suffix(" %"))
                .changed()
            {
                edit.draft.volume = percent / 100.0;
            }
            if ui.button("▶ Preview").clicked() {
                preview = true;
            }
        });
        ui.label(muted(
            &pal,
            "Multiplied by the soundboard volume. Preview plays in the headset only.",
        ));
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            if ui
                .button(RichText::new("Clear key").color(pal.bad))
                .clicked()
            {
                clear = true;
            }
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.add(accent_button(&pal, "OK")).clicked() {
                    save = true;
                }
                if ui.button("Cancel").clicked() {
                    close = true;
                }
            });
        });
    });
    if preview && let Err(e) = app.engine.player.play(&edit.draft, true) {
        app.message = Some((e, true));
    }
    if save || clear {
        let draft: Sound = if clear {
            Sound::default()
        } else {
            edit.draft.clone()
        };
        let (page, key) = (edit.page, edit.key);
        if let Some(p) = app.config.pages.get_mut(page) {
            if draft.files.is_empty() {
                p.keys.remove(&key);
            } else {
                p.keys.insert(key, draft);
            }
        }
        close = true;
    }
    if close {
        app.edit = None;
    }
}

fn pick_audio() -> Option<std::path::PathBuf> {
    rfd::FileDialog::new()
        .add_filter("Audio", &["wav", "mp3", "ogg", "flac"])
        .pick_file()
}

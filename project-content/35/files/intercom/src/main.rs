//! Intercom: a soundboard, a live voice changer and game helpers, in one window.
//!
//! Start reading here, then `app.rs` (the window) and `audio.rs` (the sound).
//! The voice effects come from the voice-changer project, used as a library.

// No black console window behind the app on Windows.
#![cfg_attr(windows, windows_subsystem = "windows")]

mod announce;
mod app;
mod audio;
mod config;
mod controller;
mod default_mic;
mod focus;
mod gate;
mod hotkeys;
mod keys;
mod media;
mod mouse;
mod platform;
mod programs;
mod settings;
mod snapshot;
mod theme;
mod ui_kit;
mod undo;
mod virtual_mic;

fn main() -> eframe::Result {
    // Windows: "Always start as administrator" (Windows asks first).
    #[cfg(windows)]
    if let Ok(Some(config)) = config::Config::load(&config::config_dir().join("config.toml"))
        && config.general.always_admin
        && !platform::is_admin()
        && platform::restart_as_admin()
    {
        return Ok(());
    }

    let options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_title("Intercom")
            .with_app_id("intercom")
            .with_inner_size([600.0, 940.0])
            .with_min_inner_size([480.0, 600.0])
            .with_drag_and_drop(true)
            .with_icon(
                eframe::icon_data::from_png_bytes(include_bytes!("../assets/icon.png"))
                    .unwrap_or_default(),
            ),
        ..Default::default()
    };
    eframe::run_native(
        "Intercom",
        options,
        Box::new(|cc| Ok(Box::new(app::App::new(cc)))),
    )
}

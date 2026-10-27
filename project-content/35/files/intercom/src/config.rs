//! Everything the user can set, as it is stored in `config.toml`.
//!
//! `#[serde(default)]` on a struct means a missing entry takes its default
//! value, so an old or hand-written file never fails because a newer
//! setting is not in it yet.

use crate::keys::Key;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use voice_changer::effect::{EffectArgs, EffectKind};

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[serde(default)]
pub struct Config {
    pub audio: AudioConfig,
    pub voice: VoiceConfig,
    pub hotkeys: Hotkeys,
    pub autoclick: AutoClick,
    pub drift: Drift,
    pub general: General,
    pub appearance: Appearance,
    #[serde(rename = "page")]
    pub pages: Vec<Page>,
}

/// Device choices. `None` means "the usual one": the system default for the
/// headset, the default real mic (never a virtual one) for the mic,
/// Intercom's virtual output for the virtual outputs.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct AudioConfig {
    pub mic: Option<String>,
    /// Silence the mic between words.
    pub noise_gate: bool,
    /// The gate opens this many dB above the mic's noise floor.
    pub gate_margin_db: f32,
    /// Where the voice changer sends your changed voice (others hear it).
    pub voice_out: Option<String>,
    /// Where the soundboard sends its sounds for others to hear.
    pub sound_out: Option<String>,
    /// What you hear: the sounds, and your voice while testing.
    pub headset: Option<String>,
    pub headset_volume: f32,
    /// Use `test_device` instead of the headset for the voice test.
    pub separate_test_device: bool,
    pub test_device: Option<String>,
    /// Audio block size in ms: smaller = less delay, larger = fewer cracks.
    pub block_ms: u32,
    pub virtual_mic: LinuxVirtualMic,
    /// Make the virtual mic (VB-Cable's "CABLE Output" on Windows) the
    /// system's default microphone while Intercom runs.
    pub virtual_mic_default: bool,
}

impl Default for AudioConfig {
    fn default() -> Self {
        AudioConfig {
            mic: None,
            noise_gate: true,
            gate_margin_db: 9.0,
            voice_out: None,
            sound_out: None,
            headset: None,
            headset_volume: 0.8,
            separate_test_device: false,
            test_device: None,
            block_ms: 10,
            virtual_mic: LinuxVirtualMic::default(),
            virtual_mic_default: false,
        }
    }
}

/// The virtual microphone Intercom creates on Linux.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct LinuxVirtualMic {
    pub name: String,
    pub create_on_start: bool,
    pub keep_after_close: bool,
}

impl Default for LinuxVirtualMic {
    fn default() -> Self {
        LinuxVirtualMic {
            name: "Intercom Mic".into(),
            create_on_start: true,
            keep_after_close: false,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug)]
pub enum EffectChoice {
    #[serde(rename = "pitch")]
    Pitch,
    #[serde(rename = "robot")]
    Robot,
    #[serde(rename = "4bit")]
    FourBit,
    #[serde(rename = "8bit")]
    EightBit,
    #[serde(rename = "16bit")]
    SixteenBit,
}

impl EffectChoice {
    pub const ALL: [EffectChoice; 5] = [
        EffectChoice::Pitch,
        EffectChoice::Robot,
        EffectChoice::FourBit,
        EffectChoice::EightBit,
        EffectChoice::SixteenBit,
    ];

    pub fn label(self) -> &'static str {
        match self {
            EffectChoice::Pitch => "Pitch",
            EffectChoice::Robot => "Robot",
            EffectChoice::FourBit => "4bit",
            EffectChoice::EightBit => "8bit",
            EffectChoice::SixteenBit => "16bit",
        }
    }

    pub fn description(self) -> &'static str {
        match self {
            EffectChoice::Pitch => "Higher or lower voice",
            EffectChoice::Robot => "One fixed note",
            EffectChoice::FourBit => "Talking toy",
            EffectChoice::EightBit => "NES, Game Boy",
            EffectChoice::SixteenBit => "SNES, Mega Drive",
        }
    }
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct VoiceConfig {
    pub effect: EffectChoice,
    pub pitch: f32,
    pub window_ms: f32,
    pub freq: f32,
    /// Console effects: `None` keeps the preset's value.
    pub bits: Option<u32>,
    pub rate: Option<u32>,
    pub on_at_start: bool,
    /// Say "Voice changer on/off" in the headset when it is switched.
    pub announce: bool,
    pub announce_volume: f32,
    /// Speak the "on" line in the new voice.
    pub announce_in_effect: bool,
    /// Your own lines instead of the built-in ones.
    pub announce_on: Option<PathBuf>,
    pub announce_off: Option<PathBuf>,
}

impl Default for VoiceConfig {
    fn default() -> Self {
        VoiceConfig {
            effect: EffectChoice::Robot,
            pitch: 5.0,
            window_ms: 30.0,
            freq: 100.0,
            bits: None,
            rate: None,
            on_at_start: false,
            announce: true,
            announce_volume: 0.7,
            announce_in_effect: true,
            announce_on: None,
            announce_off: None,
        }
    }
}

impl VoiceConfig {
    /// The same settings in the voice-changer library's terms.
    pub fn effect_args(&self) -> EffectArgs {
        EffectArgs {
            effect: match self.effect {
                EffectChoice::Pitch => EffectKind::Pitch,
                EffectChoice::Robot => EffectKind::Robot,
                EffectChoice::FourBit => EffectKind::FourBit,
                EffectChoice::EightBit => EffectKind::EightBit,
                EffectChoice::SixteenBit => EffectKind::SixteenBit,
            },
            pitch: self.pitch,
            window_ms: self.window_ms,
            freq: self.freq,
            bits: self.bits,
            rate: self.rate,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct Hotkeys {
    pub voice_toggle: Key,
    pub volume_up: Key,
    pub volume_down: Key,
    /// Percent per press.
    pub volume_step: u32,
    pub page_next: Key,
    pub page_prev: Key,
    pub stop_sound: Key,
    pub drift_left: Key,
    pub drift_right: Key,
}

impl Default for Hotkeys {
    fn default() -> Self {
        Hotkeys {
            voice_toggle: Key::F9,
            volume_up: Key::Up,
            volume_down: Key::Down,
            volume_step: 10,
            page_next: Key::PageDown,
            page_prev: Key::PageUp,
            stop_sound: Key::NumDot,
            drift_left: Key::Left,
            drift_right: Key::Right,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[serde(rename_all = "lowercase")]
pub enum MouseButton {
    Left,
    Right,
    Middle,
}

#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[serde(rename_all = "lowercase")]
pub enum ClickMode {
    Toggle,
    Hold,
}

/// Valkyrie autoclick's settings.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct AutoClick {
    pub enabled: bool,
    pub trigger: Key,
    pub button: MouseButton,
    pub mode: ClickMode,
    pub rate: f32,
    pub max_rate: f32,
    /// How long each click holds the button; `None` = half the period, at most 20 ms.
    pub press_ms: Option<f32>,
    pub faster_key: Option<Key>,
    pub slower_key: Option<Key>,
    pub mode_key: Option<Key>,
    pub step: f32,
    pub sounds: bool,
    pub sound_volume: f32,
}

impl Default for AutoClick {
    fn default() -> Self {
        AutoClick {
            enabled: true,
            trigger: Key::F17,
            button: MouseButton::Left,
            mode: ClickMode::Toggle,
            rate: 15.0,
            max_rate: 20.0,
            press_ms: None,
            faster_key: None,
            slower_key: None,
            mode_key: None,
            step: 1.0,
            sounds: true,
            sound_volume: 0.3,
        }
    }
}

/// The .NET app's mouse drift: 15 px every 20 ms.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct Drift {
    pub enabled: bool,
    pub px: i32,
    pub every_ms: u32,
}

impl Default for Drift {
    fn default() -> Self {
        Drift {
            enabled: true,
            px: 15,
            every_ms: 20,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct General {
    pub focus_only: bool,
    pub focus_program: String,
    pub keep_on_top: bool,
    pub ask_before_close: bool,
    pub start_with_windows: bool,
    pub always_admin: bool,
}

impl Default for General {
    fn default() -> Self {
        General {
            focus_only: false,
            focus_program: if cfg!(windows) {
                "SCPSL.exe".into()
            } else {
                "SCPSL.x86_64".into()
            },
            keep_on_top: false,
            ask_before_close: true,
            start_with_windows: false,
            always_admin: false,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug, Default)]
#[serde(rename_all = "lowercase")]
pub enum Theme {
    #[default]
    Dark,
    Light,
    System,
}

/// The accent color: one of the swatches, or any color.
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[serde(try_from = "String", into = "String")]
pub enum Accent {
    Amber,
    Blue,
    Teal,
    Violet,
    Rose,
    Custom([u8; 3]),
}

impl Accent {
    pub const SWATCHES: [Accent; 5] = [
        Accent::Amber,
        Accent::Blue,
        Accent::Teal,
        Accent::Violet,
        Accent::Rose,
    ];

    pub fn rgb(self) -> [u8; 3] {
        match self {
            Accent::Amber => [0xF5, 0xA5, 0x24],
            Accent::Blue => [0x5A, 0xA9, 0xF8],
            Accent::Teal => [0x2E, 0xC4, 0xB6],
            Accent::Violet => [0xA7, 0x8B, 0xFA],
            Accent::Rose => [0xF4, 0x7A, 0x9C],
            Accent::Custom(rgb) => rgb,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Accent::Amber => "Amber",
            Accent::Blue => "Blue",
            Accent::Teal => "Teal",
            Accent::Violet => "Violet",
            Accent::Rose => "Rose",
            Accent::Custom(_) => "Custom",
        }
    }
}

impl From<Accent> for String {
    fn from(accent: Accent) -> String {
        match accent {
            Accent::Custom([r, g, b]) => format!("#{r:02x}{g:02x}{b:02x}"),
            other => other.name().to_lowercase(),
        }
    }
}

impl TryFrom<String> for Accent {
    type Error = String;
    fn try_from(text: String) -> Result<Accent, String> {
        if let Some(hex) = text.strip_prefix('#')
            && hex.len() == 6
            && let Ok(v) = u32::from_str_radix(hex, 16)
        {
            return Ok(Accent::Custom([(v >> 16) as u8, (v >> 8) as u8, v as u8]));
        }
        Accent::SWATCHES
            .into_iter()
            .find(|a| a.name().eq_ignore_ascii_case(&text))
            .ok_or_else(|| format!("unknown accent `{text}`; use a color name or #rrggbb"))
    }
}

#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Debug)]
#[serde(default)]
pub struct Appearance {
    pub theme: Theme,
    pub accent: Accent,
}

impl Default for Appearance {
    fn default() -> Self {
        Appearance {
            theme: Theme::Dark,
            accent: Accent::Amber,
        }
    }
}

/// One page of sounds: what each numpad key plays.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[serde(default)]
pub struct Page {
    pub name: String,
    pub keys: BTreeMap<Key, Sound>,
}

/// What one key plays: one of `files`, picked at random each time.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct Sound {
    pub files: Vec<PathBuf>,
    pub volume: f32,
}

impl Default for Sound {
    fn default() -> Self {
        Sound {
            files: Vec::new(),
            volume: 1.0,
        }
    }
}

impl Sound {
    /// The first file's name without its folder or extension, for buttons.
    /// Splits on both `/` and `\`, so paths imported from Windows read well on Linux too.
    pub fn title(&self) -> String {
        let Some(path) = self.files.first() else {
            return String::new();
        };
        let path = path.to_string_lossy();
        let name = path.rsplit(['/', '\\']).next().unwrap_or(&path);
        match name.rsplit_once('.') {
            Some((stem, _)) if !stem.is_empty() => stem.to_string(),
            _ => name.to_string(),
        }
    }
}

impl Config {
    /// What a first start looks like: one empty page.
    pub fn first_start() -> Config {
        Config {
            pages: vec![Page {
                name: "Page 1".into(),
                keys: BTreeMap::new(),
            }],
            ..Config::default()
        }
    }

    /// Reads `path`. Returns `Ok(None)` if there is no file yet.
    pub fn load(path: &Path) -> Result<Option<Config>, String> {
        match std::fs::read_to_string(path) {
            Ok(text) => {
                let mut config: Config =
                    toml::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?;
                if config.pages.is_empty() {
                    config.pages = Config::first_start().pages;
                }
                Ok(Some(config))
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(e) => Err(format!("{}: {e}", path.display())),
        }
    }

    pub fn save(&self, path: &Path) -> Result<(), String> {
        let text = toml::to_string_pretty(self).map_err(|e| e.to_string())?;
        write_file(path, &text)
    }

    /// Every hotkey with what it does, for the conflict check.
    pub fn bound_keys(&self) -> Vec<(Key, &'static str)> {
        let h = &self.hotkeys;
        let mut keys = vec![
            (h.voice_toggle, "Voice changer on/off"),
            (h.volume_up, "Volume up"),
            (h.volume_down, "Volume down"),
            (h.page_next, "Next page"),
            (h.page_prev, "Previous page"),
            (h.stop_sound, "Stop sound"),
            (h.drift_left, "Mouse drift left"),
            (h.drift_right, "Mouse drift right"),
            (self.autoclick.trigger, "Auto-click trigger"),
        ];
        for (key, what) in [
            (self.autoclick.faster_key, "Auto-click faster"),
            (self.autoclick.slower_key, "Auto-click slower"),
            (self.autoclick.mode_key, "Auto-click mode"),
        ] {
            if let Some(key) = key {
                keys.push((key, what));
            }
        }
        keys
    }

    /// Keys used twice (sound keys count as used), with what uses them.
    pub fn conflicts(&self) -> Vec<(Key, Vec<&'static str>)> {
        let mut uses: BTreeMap<Key, Vec<&'static str>> = BTreeMap::new();
        for key in Key::SOUND_KEYS {
            if key != self.hotkeys.stop_sound {
                uses.entry(key).or_default().push("Sound key");
            }
        }
        for (key, what) in self.bound_keys() {
            uses.entry(key).or_default().push(what);
        }
        uses.into_iter().filter(|(_, u)| u.len() > 1).collect()
    }
}

/// What changes all the time and is remembered without being undoable.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct State {
    pub page: usize,
    pub sound_volume: f32,
    pub test_on: bool,
    /// The captured program's volume, in what others hear.
    pub program_volume: f32,
    /// The system's default mic before Intercom made its virtual mic the
    /// default, to give it back even after a crash.
    pub replaced_default_mic: Option<String>,
    pub reduced: Reduced,
}

impl Default for State {
    fn default() -> Self {
        State {
            page: 0,
            sound_volume: 0.6,
            test_on: false,
            program_volume: 0.5,
            replaced_default_mic: None,
            reduced: Reduced::default(),
        }
    }
}

/// The main window's blocks reduced to their title line.
#[derive(Serialize, Deserialize, Clone, Copy, Default, PartialEq, Eq, Debug)]
#[serde(default)]
pub struct Reduced {
    pub voice: bool,
    pub sounds: bool,
    pub now_playing: bool,
    pub autoclick: bool,
    pub drift: bool,
}

impl State {
    pub fn load(path: &Path) -> State {
        std::fs::read_to_string(path)
            .ok()
            .and_then(|text| toml::from_str(&text).ok())
            .unwrap_or_default()
    }

    pub fn save(&self, path: &Path) -> Result<(), String> {
        write_file(path, &toml::to_string(self).map_err(|e| e.to_string())?)
    }
}

/// `~/.config/intercom` on Linux, `%APPDATA%\intercom` on Windows.
pub fn config_dir() -> PathBuf {
    directories::BaseDirs::new()
        .map(|d| d.config_dir().join("intercom"))
        .unwrap_or_else(|| PathBuf::from("intercom"))
}

/// Writes through a temporary file, so a crash never leaves half a file.
fn write_file(path: &Path, text: &str) -> Result<(), String> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    }
    let tmp = path.with_extension("tmp");
    std::fs::write(&tmp, text).map_err(|e| format!("{}: {e}", tmp.display()))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("{}: {e}", path.display()))
}

/// Valkyrie's auto-click settings file, if it exists.
pub fn valkyrie_config() -> Option<PathBuf> {
    let path = directories::BaseDirs::new()?
        .config_dir()
        .join("valkyrie")
        .join("autoclick.toml");
    path.exists().then_some(path)
}

/// Reads Valkyrie's `autoclick.toml`: its first `[[click]]` and the shared
/// settings (highest rate, sounds), on top of `current`.
pub fn import_valkyrie(text: &str, current: &AutoClick) -> Result<AutoClick, String> {
    let table: toml::Table =
        toml::from_str(text).map_err(|e| format!("not a Valkyrie autoclick.toml: {e}"))?;
    let click = table
        .get("click")
        .and_then(|c| c.as_array())
        .and_then(|c| c.first())
        .and_then(|c| c.as_table())
        .ok_or("no [[click]] section")?;
    let number = |t: &toml::Table, name: &str| {
        t.get(name)
            .and_then(|v| v.as_float().or(v.as_integer().map(|i| i as f64)))
            .map(|v| v as f32)
    };
    let key = |name: &str| -> Result<Option<Key>, String> {
        match click.get(name).and_then(|v| v.as_str()) {
            None => Ok(None),
            Some(k) => Key::from_name(k)
                .map(Some)
                .ok_or_else(|| format!("{name}: Intercom doesn't know the key {k}")),
        }
    };
    let mut a = current.clone();
    a.trigger = key("key")?.ok_or("the [[click]] has no key")?;
    a.faster_key = key("faster_key")?;
    a.slower_key = key("slower_key")?;
    a.mode_key = key("mode_key")?;
    a.button = match click.get("button").and_then(|v| v.as_str()) {
        Some("right") => MouseButton::Right,
        Some("middle") => MouseButton::Middle,
        _ => MouseButton::Left,
    };
    a.mode = match click.get("mode").and_then(|v| v.as_str()) {
        Some("toggle") => ClickMode::Toggle,
        _ => ClickMode::Hold,
    };
    a.max_rate = number(&table, "max_rate").unwrap_or(20.0);
    a.rate = number(click, "rate")
        .unwrap_or(a.rate)
        .clamp(1.0, a.max_rate);
    a.press_ms = number(click, "press_ms");
    a.step = number(click, "step").unwrap_or(1.0);
    a.sounds = table.get("sound").and_then(|v| v.as_bool()).unwrap_or(true);
    a.sound_volume = number(&table, "volume").unwrap_or(0.3).clamp(0.0, 1.0);
    Ok(a)
}

/// Reads the old .NET app's `AudioConfig.json`: `{"0": {"1": "path", "+": ...}}`,
/// one object per page.
pub fn import_audio_config(text: &str) -> Result<Vec<Page>, String> {
    let pages: BTreeMap<String, BTreeMap<String, String>> =
        serde_json::from_str(text).map_err(|e| format!("not an AudioConfig.json: {e}"))?;
    // Page names are numbers; sort them as numbers ("10" after "9").
    let mut pages: Vec<(String, BTreeMap<String, String>)> = pages.into_iter().collect();
    pages.sort_by_key(|(name, _)| name.parse::<u32>().unwrap_or(u32::MAX));
    Ok(pages
        .into_iter()
        .enumerate()
        .map(|(i, (_, keys))| Page {
            name: format!("Imported {}", i + 1),
            keys: keys
                .into_iter()
                .filter_map(|(key, path)| {
                    let key = match key.as_str() {
                        "0" => Key::Num0,
                        "1" => Key::Num1,
                        "2" => Key::Num2,
                        "3" => Key::Num3,
                        "4" => Key::Num4,
                        "5" => Key::Num5,
                        "6" => Key::Num6,
                        "7" => Key::Num7,
                        "8" => Key::Num8,
                        "9" => Key::Num9,
                        "+" => Key::NumPlus,
                        "-" => Key::NumMinus,
                        "*" => Key::NumStar,
                        "/" => Key::NumSlash,
                        "enter" => Key::NumEnter,
                        _ => return None,
                    };
                    // The old app's placeholder for an empty key.
                    let empty = path.trim().is_empty() || path.contains("implémenter");
                    (!empty).then(|| {
                        let sound = Sound {
                            files: vec![PathBuf::from(path)],
                            volume: 1.0,
                        };
                        (key, sound)
                    })
                })
                .collect(),
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_saved_config_reads_back_the_same() {
        let mut config = Config::first_start();
        config.appearance.accent = Accent::Custom([1, 2, 255]);
        config.voice.bits = Some(4);
        config.pages[0].keys.insert(
            Key::NumPlus,
            Sound {
                files: vec!["/a/b.wav".into(), "/a/c.ogg".into()],
                volume: 0.5,
            },
        );
        let text = toml::to_string_pretty(&config).unwrap();
        assert_eq!(toml::from_str::<Config>(&text).unwrap(), config);
    }

    #[test]
    fn missing_settings_take_their_defaults() {
        let config: Config = toml::from_str("[hotkeys]\nvoice_toggle = \"F2\"\n").unwrap();
        assert_eq!(config.hotkeys.voice_toggle, Key::F2);
        assert_eq!(config.hotkeys.volume_up, Key::Up);
        assert_eq!(config.audio.headset_volume, 0.8);
    }

    #[test]
    fn imports_the_old_dotnet_file() {
        let text = r#"{
            "1": { "1": "C:\\Music\\b.wav" },
            "0": { "1": "C:\\Music\\a.wav", "+": "C:\\x.mp3", "enter": "C:\\y.ogg",
                   "2": "à implémenter", "3": "" }
        }"#;
        let pages = import_audio_config(text).unwrap();
        assert_eq!(pages.len(), 2);
        assert_eq!(pages[0].name, "Imported 1");
        assert_eq!(pages[0].keys.len(), 3);
        assert_eq!(
            pages[0].keys[&Key::Num1].files[0],
            PathBuf::from("C:\\Music\\a.wav")
        );
        assert!(pages[0].keys.contains_key(&Key::NumEnter));
        assert_eq!(pages[1].keys[&Key::Num1].title(), "b");
    }

    // Windows PowerShell and Notepad can start a UTF-8 file with a byte order mark.
    #[test]
    fn a_file_starting_with_a_byte_order_mark_loads() {
        let path = std::env::temp_dir().join(format!("intercom-bom-{}.toml", std::process::id()));
        std::fs::write(&path, "\u{feff}[hotkeys]\nvoice_toggle = \"F2\"\n").unwrap();
        let config = Config::load(&path);
        let _ = std::fs::remove_file(&path);
        assert_eq!(config.unwrap().unwrap().hotkeys.voice_toggle, Key::F2);
    }

    #[test]
    fn imports_valkyrie_autoclick() {
        let text = r#"
            swallow = true
            max_rate = 20
            sound = true
            volume = 0.6
            [[click]]
            key = "F13"
            button = "left"
            rate = 15
            mode = "hold"
            slower_key = "F14"
            faster_key = "F15"
            mode_key = "F16"
            step = 1
        "#;
        let a = import_valkyrie(text, &AutoClick::default()).unwrap();
        assert_eq!(
            (a.trigger, a.mode, a.rate),
            (Key::F13, ClickMode::Hold, 15.0)
        );
        assert_eq!(a.faster_key, Some(Key::F15));
        assert_eq!((a.sound_volume, a.press_ms), (0.6, None));
        assert!(import_valkyrie("sound = true", &a).is_err());
        assert!(import_valkyrie("[[click]]\nkey = \"Nope\"", &a).is_err());
    }

    #[test]
    fn a_hotkey_on_a_sound_key_is_a_conflict() {
        let mut config = Config::first_start();
        assert!(config.conflicts().is_empty());
        config.autoclick.trigger = Key::F9;
        config.hotkeys.drift_left = Key::Num4;
        let conflicts = config.conflicts();
        assert_eq!(conflicts.len(), 2);
        assert!(conflicts.iter().any(|(k, _)| *k == Key::F9));
        assert!(conflicts.iter().any(|(k, _)| *k == Key::Num4));
    }
}

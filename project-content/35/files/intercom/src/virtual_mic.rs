//! The virtual microphone games and Discord listen to.
//!
//! On Linux, Intercom creates it with two PulseAudio modules (PipeWire
//! understands them too): a "null sink", a speaker that plays nowhere, which
//! Intercom plays into; and a "remap source" that turns what that speaker
//! plays into a microphone. They are removed when Intercom closes, unless
//! the user asked to keep them. After a crash they are found by name on the
//! next start and reused.
//!
//! On Windows nothing can be created: VB-Audio Virtual Cable must be
//! installed, and Intercom only looks for it.

/// The name Intercom gives its virtual output (what it plays into).
pub const OUTPUT_DESCRIPTION: &str = "Intercom Output";
#[cfg(target_os = "linux")]
const SINK_NAME: &str = "intercom_output";
/// The virtual mic's system name.
#[cfg(target_os = "linux")]
pub const SOURCE_NAME: &str = "intercom_mic";

#[derive(Clone, Debug, PartialEq)]
pub enum Status {
    /// Not created (turned off in the settings).
    Off,
    /// Linux: the devices exist. `modules` are their PulseAudio module numbers.
    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    Ready { modules: Vec<u32>, created: bool },
    /// Windows: VB-Cable was found.
    #[cfg_attr(not(windows), allow(dead_code))]
    CableFound,
    /// Windows: no VB-Cable.
    CableMissing,
    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    Failed(String),
}

impl Status {
    /// The name of the output Intercom should play into, if there is one.
    pub fn output_name(&self) -> Option<&'static str> {
        match self {
            Status::Ready { .. } => Some(OUTPUT_DESCRIPTION),
            Status::CableFound => Some("CABLE Input"),
            _ => None,
        }
    }
}

pub struct VirtualMic {
    pub status: Status,
    keep: bool,
}

impl VirtualMic {
    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn none() -> VirtualMic {
        VirtualMic {
            status: Status::Off,
            keep: true,
        }
    }

    /// Linux: creates (or reuses) the devices. Windows: looks for VB-Cable.
    pub fn setup(config: &crate::config::LinuxVirtualMic, outputs: &[String]) -> VirtualMic {
        #[cfg(target_os = "linux")]
        {
            let _ = outputs;
            if !config.create_on_start {
                return VirtualMic::none();
            }
            let status = linux::create(&config.name).unwrap_or_else(Status::Failed);
            VirtualMic {
                status,
                keep: config.keep_after_close,
            }
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = config;
            let found = outputs.iter().any(|name| name.contains("CABLE Input"));
            VirtualMic {
                status: if found {
                    Status::CableFound
                } else {
                    Status::CableMissing
                },
                keep: true,
            }
        }
    }

    pub fn set_keep(&mut self, keep: bool) {
        self.keep = keep;
    }

    /// Removes the devices now (unless they are to be kept).
    pub fn close(&mut self) {
        #[cfg(target_os = "linux")]
        if let Status::Ready { modules, .. } = &self.status
            && !self.keep
        {
            linux::remove(modules);
        }
        self.status = Status::Off;
    }
}

impl Drop for VirtualMic {
    fn drop(&mut self) {
        self.close();
    }
}

#[cfg(target_os = "linux")]
pub(crate) use linux::pactl;

#[cfg(target_os = "linux")]
mod linux {
    use super::{OUTPUT_DESCRIPTION, SINK_NAME, SOURCE_NAME, Status};
    use std::process::Command;

    /// Runs `pactl` and returns what it printed.
    pub(crate) fn pactl(args: &[&str]) -> Result<String, String> {
        let out = Command::new("pactl").args(args).output().map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                "pactl is missing. Install it (Debian/Ubuntu: sudo apt install pulseaudio-utils)"
                    .to_string()
            } else {
                format!("pactl: {e}")
            }
        })?;
        if out.status.success() {
            Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
        } else {
            Err(format!(
                "pactl {}: {}",
                args.first().unwrap_or(&""),
                String::from_utf8_lossy(&out.stderr).trim()
            ))
        }
    }

    /// Module arguments set `device.description="name"`; quotes in the name would break them.
    fn clean(name: &str) -> String {
        let name: String = name
            .chars()
            .filter(|c| !matches!(c, '"' | '\'' | '\\'))
            .collect();
        let name = name.trim();
        if name.is_empty() {
            "Intercom Mic".into()
        } else {
            name.to_string()
        }
    }

    /// Intercom's modules already loaded: (number, arguments).
    fn ours() -> Result<Vec<(u32, String)>, String> {
        Ok(pactl(&["list", "short", "modules"])?
            .lines()
            .filter_map(|line| {
                let mut parts = line.split('\t');
                let id = parts.next()?.trim().parse().ok()?;
                let _module = parts.next()?;
                let args = parts.next().unwrap_or("").to_string();
                let mine = args.contains(&format!("sink_name={SINK_NAME}"))
                    || args.contains(&format!("source_name={SOURCE_NAME}"));
                mine.then_some((id, args))
            })
            .collect())
    }

    pub fn create(mic_name: &str) -> Result<Status, String> {
        let mic_name = clean(mic_name);
        let sink_args = format!("sink_properties='device.description=\"{OUTPUT_DESCRIPTION}\"'");
        let source_args = format!("source_properties='device.description=\"{mic_name}\"'");

        // Left over from a crash, or kept on purpose: reuse them if they match.
        let existing = ours()?;
        if existing.len() == 2 && existing.iter().any(|(_, a)| a.contains(&source_args)) {
            let mut modules: Vec<u32> = existing.iter().map(|(id, _)| *id).collect();
            modules.sort();
            unmute();
            return Ok(Status::Ready {
                modules,
                created: false,
            });
        }
        remove(&existing.iter().map(|(id, _)| *id).collect::<Vec<_>>());

        let sink: u32 = pactl(&[
            "load-module",
            "module-null-sink",
            &format!("sink_name={SINK_NAME}"),
            &sink_args,
        ])?
        .parse()
        .map_err(|_| "pactl returned no module number".to_string())?;
        let source = pactl(&[
            "load-module",
            "module-remap-source",
            &format!("master={SINK_NAME}.monitor"),
            &format!("source_name={SOURCE_NAME}"),
            &source_args,
        ]);
        match source.and_then(|s| s.parse::<u32>().map_err(|_| "no module number".into())) {
            Ok(source) => {
                unmute();
                Ok(Status::Ready {
                    modules: vec![sink, source],
                    created: true,
                })
            }
            Err(e) => {
                remove(&[sink]);
                Err(e)
            }
        }
    }

    /// Unmutes both devices and sets them to 100 %. PipeWire remembers mute and
    /// volume per device name, so a "mute microphone" key pressed once can
    /// otherwise bring the virtual mic back muted on every start: games would
    /// then hear nothing at all. The session manager restores that saved state
    /// a moment after the device appears, sometimes after this runs, so it is
    /// done again a few times during the first seconds (in the background).
    fn unmute() {
        let once = || {
            let _ = pactl(&["set-sink-mute", SINK_NAME, "0"]);
            let _ = pactl(&["set-sink-volume", SINK_NAME, "100%"]);
            let _ = pactl(&["set-source-mute", SOURCE_NAME, "0"]);
            let _ = pactl(&["set-source-volume", SOURCE_NAME, "100%"]);
        };
        once();
        std::thread::spawn(move || {
            for ms in [300, 700, 1500, 3000] {
                std::thread::sleep(std::time::Duration::from_millis(ms));
                once();
            }
        });
    }

    /// Unloads modules, newest first (the mic depends on the speaker).
    pub fn remove(modules: &[u32]) {
        let mut modules = modules.to_vec();
        modules.sort();
        for id in modules.iter().rev() {
            let _ = pactl(&["unload-module", &id.to_string()]);
        }
    }

    #[cfg(test)]
    mod tests {
        #[test]
        fn names_cannot_break_the_module_arguments() {
            assert_eq!(super::clean("My \"cool\" mic"), "My cool mic");
            assert_eq!(super::clean("  "), "Intercom Mic");
        }
    }
}

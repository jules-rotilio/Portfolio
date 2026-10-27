//! Saves benchmark results in the "speech-bench/1" JSON format that all three
//! apps share, so their numbers can be compared side by side.
//!
//! Each run becomes one file in `benchmarks/results/voice-changer/`, e.g.
//! `20261012T171937_pitch-shift_delay-line_live.json` (the effect's method is
//! in the name, so a robot run is `..._robot_zero-phase-fft_live.json`). The format is described
//! in `tts-virtual-mic/tts_mic/metrics.py`.
//!
//! JSON is written with the `serde` library. Adding `#[derive(Serialize)]` above
//! a struct makes serde generate the code that turns it into JSON: every
//! field becomes a key with the same name. `serde_json` then writes it out.

use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

/// `benchmarks/results/voice-changer/` inside this project's folder.
/// `env!("CARGO_MANIFEST_DIR")` is filled in by the compiler with the folder
/// holding Cargo.toml, so this works wherever you run the program from.
pub fn default_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("benchmarks")
        .join("results")
        .join("voice-changer")
}

/// Summary of many measurements of one metric.
#[derive(Serialize)]
pub struct Stats {
    pub mean: f64,
    pub p50: f64,
    pub p95: f64,
    pub min: f64,
    pub max: f64,
}

impl Stats {
    /// Returns `None` when there are no values (nothing to summarise).
    pub fn from_values(values: &[f64]) -> Option<Stats> {
        if values.is_empty() {
            return None;
        }
        let mut sorted = values.to_vec();
        sorted.sort_by(|a, b| a.total_cmp(b));
        let pick = |p: f64| sorted[(p * (sorted.len() - 1) as f64).round() as usize];
        Some(Stats {
            mean: round3(sorted.iter().sum::<f64>() / sorted.len() as f64),
            p50: round3(pick(0.50)),
            p95: round3(pick(0.95)),
            min: round3(sorted[0]),
            max: round3(sorted[sorted.len() - 1]),
        })
    }
}

#[derive(Serialize)]
struct Machine {
    os: String,
    cpu: String,
    cores: usize,
    arch: String,
    ram_gb: f64,
}

/// One benchmark run. The field names are the JSON keys, so they must match
/// the shared format exactly. `Option<f64>` becomes a number, or `null` for None.
#[derive(Serialize)]
pub struct Report {
    schema: &'static str,
    app: &'static str,
    implementation: &'static str,
    /// Which method produced the audio, e.g. "pitch-shift:delay-line".
    engine: &'static str,
    pub mode: String,
    created: String,
    machine: Machine,
    /// Time to get ready before processing audio (opening devices etc.).
    pub load_ms: f64,
    cpu_time_s: Option<f64>,
    peak_rss_mb: Option<f64>,
    /// `BTreeMap` is a dictionary kept sorted by key: metric name → Stats.
    pub summary: BTreeMap<String, Stats>,
    /// Time series, one entry per second. `Value` is "any JSON value".
    pub samples: Vec<Value>,
    /// Extra fields beyond the shared ones: the options used, and event counts.
    pub settings: Value,
    pub counters: BTreeMap<String, u64>,
}

impl Report {
    pub fn new(mode: &str, engine: &'static str) -> Report {
        Report {
            schema: "speech-bench/1",
            app: "voice-changer",
            implementation: "rust",
            engine,
            mode: mode.to_string(),
            created: String::new(),
            machine: machine(),
            load_ms: 0.0,
            cpu_time_s: None,
            peak_rss_mb: None,
            summary: BTreeMap::new(),
            samples: Vec::new(),
            settings: Value::Null,
            counters: BTreeMap::new(),
        }
    }

    /// Adds a metric to the summary (skipped if there were no measurements).
    pub fn add(&mut self, name: &str, values: &[f64]) {
        if let Some(stats) = Stats::from_values(values) {
            self.summary.insert(name.to_string(), stats);
        }
    }

    /// Prints the summary as a small table.
    pub fn print(&self) {
        println!(
            "{:<26} {:>10} {:>10} {:>10} {:>10}",
            "metric", "mean", "p50", "p95", "max"
        );
        for (name, s) in &self.summary {
            println!(
                "{name:<26} {:>10.3} {:>10.3} {:>10.3} {:>10.3}",
                s.mean, s.p50, s.p95, s.max
            );
        }
        for (name, n) in &self.counters {
            println!("{name:<26} {n:>10}");
        }
    }

    /// Fills in the time, CPU and memory figures, then writes the JSON file.
    pub fn save(mut self, dir: &Path) -> std::io::Result<PathBuf> {
        let (cpu, rss) = process_usage();
        self.cpu_time_s = cpu.map(round3);
        self.peak_rss_mb = rss.map(|mb| (mb * 10.0).round() / 10.0);

        // "2026-10-12T17:19:37Z" → "2026-10-12T17:19:37+00:00" (same style as Python)
        let stamp = humantime::format_rfc3339_seconds(SystemTime::now()).to_string();
        self.created = stamp.replace('Z', "+00:00");
        let compact: String = stamp
            .chars()
            .filter(|c| c.is_ascii_alphanumeric())
            .collect();
        let compact = compact.trim_end_matches('Z'); // "20261012T171937"

        // `to_string_pretty` produces indented JSON; `?` turns a failure into an error.
        let json = serde_json::to_string_pretty(&self).map_err(std::io::Error::other)?;
        let engine = self.engine.replace([':', '/'], "_");
        write_new(dir, &format!("{compact}_{engine}_{}", self.mode), &json)
    }
}

/// Writes `contents` to `<dir>/<stem>.json` and returns its path. Two runs
/// started in the same second get the same stem, so if that file already
/// exists we try `<stem>_2.json`, `<stem>_3.json`... `File::create_new` only
/// creates a file that isn't there yet, so even two programs saving at the
/// very same moment can't overwrite each other.
fn write_new(dir: &Path, stem: &str, contents: &str) -> std::io::Result<PathBuf> {
    std::fs::create_dir_all(dir)?;
    let mut n = 1;
    loop {
        let suffix = if n == 1 {
            String::new()
        } else {
            format!("_{n}")
        };
        let path = dir.join(format!("{stem}{suffix}.json"));
        match File::create_new(&path) {
            Ok(mut file) => {
                file.write_all(contents.as_bytes())?;
                return Ok(path);
            }
            Err(e) if e.kind() == ErrorKind::AlreadyExists => n += 1,
            Err(e) => return Err(e),
        }
    }
}

/// Total CPU time used by this program so far, in seconds.
pub fn cpu_time_s() -> Option<f64> {
    process_usage().0
}

/// Asks the operating system how much CPU time and peak memory this process
/// has used. This calls a C function (`getrusage`) through the `libc` crate.
/// Calling C code is `unsafe` in Rust: the compiler can't check it, so we
/// promise it is fine. Here it only fills in the struct we hand it.
/// `#[cfg(unix)]` means "only compile this on Linux/macOS".
#[cfg(unix)]
fn process_usage() -> (Option<f64>, Option<f64>) {
    let mut usage: libc::rusage = unsafe { std::mem::zeroed() };
    if unsafe { libc::getrusage(libc::RUSAGE_SELF, &mut usage) } != 0 {
        return (None, None);
    }
    let secs = |t: libc::timeval| t.tv_sec as f64 + t.tv_usec as f64 / 1e6;
    let cpu = secs(usage.ru_utime) + secs(usage.ru_stime);
    // Linux reports peak memory in kilobytes, macOS in bytes.
    let per_mb = if cfg!(target_os = "macos") {
        1024.0 * 1024.0
    } else {
        1024.0
    };
    (Some(cpu), Some(usage.ru_maxrss as f64 / per_mb))
}

/// On other systems (Windows) we report `null` for these two numbers.
#[cfg(not(unix))]
fn process_usage() -> (Option<f64>, Option<f64>) {
    (None, None)
}

fn machine() -> Machine {
    let mut sys = sysinfo::System::new();
    sys.refresh_cpu_all();
    sys.refresh_memory();
    Machine {
        os: sysinfo::System::long_os_version().unwrap_or_else(|| std::env::consts::OS.into()),
        cpu: sys
            .cpus()
            .first()
            .map(|c| c.brand().trim().to_string())
            .unwrap_or_default(),
        cores: std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(0),
        arch: std::env::consts::ARCH.into(),
        ram_gb: (sys.total_memory() as f64 / (1u64 << 30) as f64 * 10.0).round() / 10.0,
    }
}

pub fn round3(x: f64) -> f64 {
    (x * 1000.0).round() / 1000.0
}

pub fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Saving three times under the same name keeps all three files.
    #[test]
    fn same_name_gets_a_number_instead_of_overwriting() {
        let dir = std::env::temp_dir().join(format!("voice-changer-test-{}", std::process::id()));
        let paths: Vec<PathBuf> = ["a", "b", "c"]
            .iter()
            .map(|text| write_new(&dir, "run", text).unwrap())
            .collect();
        let names: Vec<_> = paths.iter().map(|p| p.file_name().unwrap()).collect();
        assert_eq!(names, ["run.json", "run_2.json", "run_3.json"]);
        let texts: Vec<String> = paths
            .iter()
            .map(|p| std::fs::read_to_string(p).unwrap())
            .collect();
        assert_eq!(texts, ["a", "b", "c"]);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}

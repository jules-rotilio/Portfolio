//! Chooses which voice effect to run, and gathers the options that belong to it.
//!
//! `live`, `bench` and `file` all take the same effect options, so they are
//! declared once here (`EffectArgs`) and each command pulls them in with
//! `#[command(flatten)]`. To add an effect: add a variant to `EffectKind` and
//! to `Effect`, then fill in the `match` in each function below.

use crate::pitch::PitchShifter;
use crate::retro::{Retro, RetroSettings};
use crate::robot::{MAX_FREQ_HZ, MIN_FREQ_HZ, Robot};
use clap::{Args, ValueEnum};
use serde_json::{Value, json};

/// The effects you can pick with `--effect`. `ValueEnum` lets clap turn the
/// text the user types (`pitch`, `robot`) into one of these variants.
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
pub enum EffectKind {
    /// Raise or lower the voice (see --pitch, --window-ms)
    Pitch,
    /// Flatten the voice to one fixed pitch, like a machine (see --freq)
    Robot,
    // `#[value(name = ...)]` sets the text to type, since a Rust name can't start with a digit.
    /// Even cruder than 8bit: a muffled, whistly voice, like a cheap talking toy (see --bits, --rate)
    #[value(name = "4bit")]
    FourBit,
    /// Dull, buzzy voice clip from an 8-bit console like the NES (see --bits, --rate)
    #[value(name = "8bit")]
    EightBit,
    /// Softer, muffled voice clip from a 16-bit console like the SNES (see --bits, --rate)
    #[value(name = "16bit")]
    SixteenBit,
}

/// Everything the user can set about the effect on the command line.
#[derive(Args, Clone)]
pub struct EffectArgs {
    /// Which voice effect to apply
    #[arg(short, long, value_enum, default_value_t = EffectKind::Pitch)]
    pub effect: EffectKind,
    /// Pitch effect: change in semitones (+12 = one octave up, -12 = one octave down)
    #[arg(short, long, default_value_t = 5.0, allow_negative_numbers = true)]
    pub pitch: f32,
    /// Pitch effect: shifter window in ms. Smaller = less delay, larger = smoother voice
    #[arg(long, default_value_t = 30.0)]
    pub window_ms: f32,
    /// Robot effect: the fixed pitch of the monotone voice, in Hz. Lower = deeper
    /// and slower to respond (about 20 ms delay at 100 Hz, 11 ms at 200 Hz)
    #[arg(long, default_value_t = 100.0, value_parser = parse_freq)]
    pub freq: f32,
    /// 4bit/8bit/16bit effects: bits per sample. Fewer = grittier; the real consoles
    /// had about 4 (8-bit era) or 8 (16-bit era) [default: 16]
    #[arg(long, value_parser = clap::value_parser!(u32).range(1..=16))]
    pub bits: Option<u32>,
    /// 4bit/8bit/16bit effects: the console's sample rate in Hz. Lower = duller, with more
    /// metallic whistles [default: 4000 for 4bit, 8000 for 8bit, 12000 for 16bit]
    #[arg(long, value_parser = clap::value_parser!(u32).range(1000..=48_000))]
    pub rate: Option<u32>,
}

/// Checks `--freq` while the command line is being read, so a bad value
/// gives a clear message instead of a strange sound.
fn parse_freq(text: &str) -> Result<f32, String> {
    let freq: f32 = text
        .parse()
        .map_err(|_| format!("`{text}` is not a number"))?;
    if (MIN_FREQ_HZ..=MAX_FREQ_HZ).contains(&freq) {
        Ok(freq)
    } else {
        Err(format!(
            "{freq} Hz is out of range; use {MIN_FREQ_HZ} to {MAX_FREQ_HZ} Hz"
        ))
    }
}

impl EffectArgs {
    /// The 4bit/8bit/16bit settings: the chosen preset, with `--bits` and
    /// `--rate` replacing its values when given. `unwrap_or` takes what's
    /// inside an `Option`, or the value in brackets if it's `None`.
    fn retro(&self) -> RetroSettings {
        let preset = match self.effect {
            EffectKind::FourBit => RetroSettings::FOUR_BIT,
            EffectKind::SixteenBit => RetroSettings::SIXTEEN_BIT,
            _ => RetroSettings::EIGHT_BIT,
        };
        RetroSettings {
            bits: self.bits.unwrap_or(preset.bits),
            rate_hz: self.rate.unwrap_or(preset.rate_hz),
            ..preset
        }
    }

    /// Short description for the "Running: ..." line.
    pub fn summary(&self) -> String {
        match self.effect {
            EffectKind::Pitch => format!("pitch {:+} semitones", self.pitch),
            EffectKind::Robot => format!("robot voice at {} Hz", self.freq),
            EffectKind::FourBit | EffectKind::EightBit | EffectKind::SixteenBit => {
                let r = self.retro();
                format!(
                    "{} console voice, {}-bit samples at {} Hz",
                    r.name, r.bits, r.rate_hz
                )
            }
        }
    }

    /// Name of the method, stored in the results file (and its file name).
    pub fn engine(&self) -> &'static str {
        match self.effect {
            EffectKind::Pitch => "pitch-shift:delay-line",
            EffectKind::Robot => "robot:zero-phase-fft",
            EffectKind::FourBit => "4bit:bitcrush-hold",
            EffectKind::EightBit => "8bit:bitcrush-hold",
            EffectKind::SixteenBit => "16bit:bitcrush-slide",
        }
    }

    /// The options that matter for this effect, for the results file.
    pub fn settings(&self) -> Value {
        match self.effect {
            EffectKind::Pitch => json!({
                "effect": "pitch",
                "pitch_semitones": self.pitch,
                "window_ms": self.window_ms,
            }),
            EffectKind::Robot => json!({
                "effect": "robot",
                "robot_freq_hz": self.freq,
            }),
            EffectKind::FourBit | EffectKind::EightBit | EffectKind::SixteenBit => {
                let r = self.retro();
                json!({
                    "effect": r.name,
                    "retro_bits": r.bits,
                    "retro_rate_hz": r.rate_hz,
                })
            }
        }
    }
}

/// A running effect: the chosen one, with its memory (buffers) ready to go.
/// An `enum` holds exactly one of its variants, so we can pick the effect
/// while the program runs and still call the same methods on it.
pub enum Effect {
    Pitch(PitchShifter),
    /// Boxed because its FFT tables make it much bigger than the pitch shifter.
    Robot(Box<Robot>),
    /// `4bit`, `8bit` and `16bit`: the same code with different settings.
    Retro(Retro),
}

impl Effect {
    pub fn new(args: &EffectArgs, sample_rate: u32) -> Effect {
        match args.effect {
            EffectKind::Pitch => {
                Effect::Pitch(PitchShifter::new(sample_rate, args.pitch, args.window_ms))
            }
            EffectKind::Robot => Effect::Robot(Box::new(Robot::new(sample_rate, args.freq))),
            EffectKind::FourBit | EffectKind::EightBit | EffectKind::SixteenBit => {
                Effect::Retro(Retro::new(sample_rate, &args.retro()))
            }
        }
    }

    /// Processes a block of samples in place.
    pub fn process(&mut self, samples: &mut [f32]) {
        match self {
            Effect::Pitch(e) => e.process(samples),
            Effect::Robot(e) => e.process(samples),
            Effect::Retro(e) => e.process(samples),
        }
    }

    /// The extra delay the effect adds by itself, in milliseconds.
    pub fn algorithmic_latency_ms(&self, sample_rate: u32) -> f32 {
        match self {
            Effect::Pitch(e) => e.algorithmic_latency_ms(sample_rate),
            Effect::Robot(e) => e.algorithmic_latency_ms(sample_rate),
            Effect::Retro(e) => e.algorithmic_latency_ms(sample_rate),
        }
    }
}

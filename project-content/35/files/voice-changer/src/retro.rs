//! The retro voice: you, as an old games console would have played you back.
//!
//! How it works (in plain words):
//! Consoles of the 8-bit and 16-bit eras had very little memory, so their
//! voice clips were stored with few samples per second and few levels per
//! sample. Those two savings are what give them their sound, and both are
//! easy to copy:
//!
//! 1. **Fewer samples per second.** The "chip" takes one sample every
//!    `sample_rate / rate` of ours. At 8000 Hz nothing above 4000 Hz fits, so
//!    the voice turns dull. Higher sounds, like "s", don't simply vanish:
//!    they fold back down as metallic whistles (this is called aliasing).
//! 2. **Fewer levels.** Each chip sample is rounded to the nearest step.
//!    4 bits gives 8 steps above zero and 8 below, and the rounding error
//!    is the grit. Old voice clips were recorded loud, to use every step,
//!    while a microphone is usually much quieter. So the steps are sized to
//!    how loud you are right now (the "envelope"), not to the loudest sound
//!    possible: a quiet voice gets as many steps as a loud one. The presets
//!    keep 16 bits, too fine to hear, so there is only grit if you lower `--bits`.
//! 3. **Playing it back.** The 4-bit and 8-bit presets hold each chip sample
//!    until the next one, which cuts the wave into stair-steps: harsh and
//!    buzzy. The 16-bit preset averages the samples between two chip samples
//!    instead of skipping them, and slides from one chip sample to the next:
//!    softer and a little muffled, like the SNES.

/// The settings of the effect. `--effect 4bit`, `8bit` and `16bit` start
/// from one of the presets below, then `--bits` and `--rate` can change them.
#[derive(Clone, Copy)]
pub struct RetroSettings {
    /// Shown in the "Running: ..." line and the results file.
    pub name: &'static str,
    /// Samples per second the chip keeps.
    pub rate_hz: u32,
    /// Bits per chip sample: 2^(bits - 1) steps on each side of zero.
    pub bits: u32,
    /// Average going in and slide coming out (16-bit), instead of skip and hold (8-bit).
    pub smooth: bool,
}

/// Bits per chip sample unless `--bits` says otherwise. At 16 the rounding is
/// far too fine to hear, so the presets differ only in rate and playback.
const PRESET_BITS: u32 = 16;

impl RetroSettings {
    /// Cruder than any console: half the rate of `8bit`, so nothing above 2000 Hz.
    pub const FOUR_BIT: Self = Self {
        name: "4bit",
        rate_hz: 4000,
        bits: PRESET_BITS,
        smooth: false,
    };
    /// NES and Game Boy voice clips: low rate, hard steps. Those consoles also
    /// had very few levels; `--bits 4` adds that grit.
    pub const EIGHT_BIT: Self = Self {
        name: "8bit",
        rate_hz: 8000,
        bits: PRESET_BITS,
        smooth: false,
    };
    /// SNES and Mega Drive voice clips: a higher rate, and smoothed. Their
    /// samples had about 8 bits' worth of levels; `--bits 8` adds that grit.
    pub const SIXTEEN_BIT: Self = Self {
        name: "16bit",
        rate_hz: 12_000,
        bits: PRESET_BITS,
        smooth: true,
    };
}

/// How fast the envelope falls when you get quieter: it halves every this many seconds.
const RELEASE_S: f32 = 0.1;
/// The smallest envelope. Without it, digital silence would mean dividing by zero.
const MIN_ENVELOPE: f32 = 1e-3;

pub struct Retro {
    /// Where we are between two chip samples, from 0.0 to 1.0.
    phase: f32,
    /// How much `phase` moves per sample: `rate / sample_rate`.
    phase_step: f32,
    /// See `RetroSettings::smooth`.
    smooth: bool,
    /// Steps on each side of zero.
    steps: f32,
    /// How loud the voice is right now: the recent peak.
    envelope: f32,
    /// What the envelope is multiplied by at each chip sample, so it falls
    /// slowly after a peak.
    release: f32,
    /// Sum and count of our samples since the last chip sample, for averaging.
    sum: f32,
    count: u32,
    /// The latest chip sample, and the one before it.
    current: f32,
    previous: f32,
}

impl Retro {
    pub fn new(sample_rate: u32, settings: &RetroSettings) -> Self {
        // A chip faster than the sound card would have nothing to drop.
        let rate = settings.rate_hz.min(sample_rate) as f32;
        Retro {
            phase: 0.0,
            phase_step: rate / sample_rate as f32,
            smooth: settings.smooth,
            steps: 2f32.powi(settings.bits as i32 - 1),
            envelope: 0.0,
            release: 0.5f32.powf(1.0 / (RELEASE_S * rate)),
            sum: 0.0,
            count: 0,
            current: 0.0,
            previous: 0.0,
        }
    }

    /// The extra delay this effect adds, in milliseconds (well under one).
    /// Holding a chip sample delays it by half a chip sample on average.
    /// Averaging delays by half a chip sample too, and sliding toward the
    /// latest chip sample means we are always one behind it.
    pub fn algorithmic_latency_ms(&self, sample_rate: u32) -> f32 {
        let chip_samples = if self.smooth { 1.5 } else { 0.5 };
        chip_samples / (self.phase_step * sample_rate as f32) * 1000.0
    }

    /// Processes a block of samples in place.
    pub fn process(&mut self, samples: &mut [f32]) {
        for s in samples.iter_mut() {
            *s = self.process_sample(*s);
        }
    }

    #[inline]
    fn process_sample(&mut self, input: f32) -> f32 {
        self.sum += input;
        self.count += 1;
        self.phase += self.phase_step;
        if self.phase >= 1.0 {
            // Time for the chip to take a sample: the average of ours since
            // the last one (16-bit), or just this one (8-bit).
            self.phase -= 1.0;
            let value = if self.smooth {
                self.sum / self.count as f32
            } else {
                input
            };
            self.sum = 0.0;
            self.count = 0;
            self.previous = self.current;
            self.current = self.quantize(value);
        }
        if self.smooth {
            // `phase` goes from 0 to 1 between two chip samples, so this
            // slides in a straight line from the previous one to the latest.
            self.previous + (self.current - self.previous) * self.phase
        } else {
            self.current
        }
    }

    /// Rounds a chip sample to the nearest step, with steps sized to the envelope.
    #[inline]
    fn quantize(&mut self, x: f32) -> f32 {
        self.envelope = (self.envelope * self.release).max(x.abs());
        let step = self.envelope.max(MIN_ENVELOPE) / self.steps;
        (x / step).round() * step
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testutil::{detect_pitch, harmonic_voice, rms, sine};

    /// The 8-bit preset with another number of bits.
    fn eight_bit(bits: u32) -> RetroSettings {
        RetroSettings {
            bits,
            ..RetroSettings::EIGHT_BIT
        }
    }

    /// The rounding error with `bits` bits, relative to the voice. The
    /// timing is the same whatever the bits, so comparing with a 16-bit
    /// version leaves only the rounding.
    fn grit(voice: &[f32], bits: u32) -> f32 {
        let sr = 48_000;
        let (mut fine, mut coarse) = (voice.to_vec(), voice.to_vec());
        Retro::new(sr, &eight_bit(16)).process(&mut fine);
        Retro::new(sr, &eight_bit(bits)).process(&mut coarse);
        let error: Vec<f32> = fine.iter().zip(&coarse).map(|(a, b)| a - b).collect();
        rms(&error) / rms(voice)
    }

    // At 8000 Hz on a 48 kHz stream, each chip sample is held for 6 of ours,
    // so the output changes value 8000 times a second.
    #[test]
    fn output_changes_at_the_chip_rate() {
        let sr = 48_000;
        let mut x = sine(440.0, sr, 1.0);
        Retro::new(sr, &eight_bit(16)).process(&mut x);
        let changes = x.windows(2).filter(|w| w[0] != w[1]).count();
        assert!((7990..=8000).contains(&changes), "{changes} changes");
    }

    // Each bit fewer doubles the step size, so 4 bits is 16 times grittier than 8.
    #[test]
    fn each_bit_fewer_doubles_the_grit() {
        let voice = harmonic_voice(|_| 150.0, 48_000, 1.0);
        let ratio = grit(&voice, 4) / grit(&voice, 8);
        assert!(
            (12.0..20.0).contains(&ratio),
            "4 bits is {ratio}x grittier than 8"
        );
    }

    #[test]
    fn a_quiet_voice_gets_as_many_steps_as_a_loud_one() {
        let loud = harmonic_voice(|_| 150.0, 48_000, 1.0);
        let quiet: Vec<f32> = loud.iter().map(|s| s * 0.05).collect();
        let ratio = grit(&quiet, 4) / grit(&loud, 4);
        assert!(
            (0.9..1.1).contains(&ratio),
            "quiet voice is {ratio}x grittier"
        );
    }

    // A tone above half the chip rate doesn't fit, so it folds back down:
    // 7500 Hz kept 8000 times a second comes out as a 500 Hz whistle.
    #[test]
    fn high_tones_fold_down_into_whistles() {
        let sr = 48_000;
        let mut x = sine(7500.0, sr, 1.0);
        Retro::new(sr, &eight_bit(16)).process(&mut x);
        let f = detect_pitch(&x, sr);
        assert!((f - 500.0).abs() < 5.0, "got {f} Hz");
    }

    // The 16-bit preset slides between chip samples, so it moves in small
    // moves where the 8-bit one jumps.
    #[test]
    fn sixteen_bit_slides_instead_of_jumping() {
        let sr = 48_000;
        let biggest_move = |settings: &RetroSettings| {
            let mut x = sine(1000.0, sr, 0.5);
            let settings = RetroSettings {
                bits: 16,
                ..*settings
            };
            Retro::new(sr, &settings).process(&mut x);
            x.windows(2)
                .map(|w| (w[1] - w[0]).abs())
                .fold(0.0, f32::max)
        };
        let rough = biggest_move(&RetroSettings::EIGHT_BIT);
        let smooth = biggest_move(&RetroSettings::SIXTEEN_BIT);
        assert!(smooth < rough / 3.0, "8-bit moves {rough}, 16-bit {smooth}");
    }

    #[test]
    fn silence_stays_silent() {
        for settings in [
            RetroSettings::FOUR_BIT,
            RetroSettings::EIGHT_BIT,
            RetroSettings::SIXTEEN_BIT,
        ] {
            let mut x = vec![0.0; 10_000];
            Retro::new(48_000, &settings).process(&mut x);
            assert!(x.iter().all(|&s| s == 0.0));
        }
    }
}

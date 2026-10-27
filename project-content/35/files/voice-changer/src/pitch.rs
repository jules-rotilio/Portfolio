//! The pitch shifter: the part that actually changes your voice.
//!
//! How it works (in plain words):
//! We keep the last few milliseconds of audio in a "delay line" (a circular
//! buffer). Normally you would read it back at the same speed you write it,
//! which gives you your own voice back. To raise the pitch we read it back
//! *faster* than we write it (like playing a record too fast); to lower the
//! pitch we read it *slower*. Reading faster would eventually overtake the
//! writing position, so the read position keeps jumping back. To hide those
//! jumps we use two read positions ("heads") half a window apart and
//! smoothly fade between them. This is called a delay-line or granular
//! pitch shifter. It is cheap (a few multiplications per sample) and adds
//! only about half a window of delay, which is what we want for real time.

use std::f32::consts::PI;

/// `pub struct` declares a data type other files can use. Each field has a
/// name and a type. `f32` is a 32-bit decimal number, `usize` is a whole
/// number used for positions in memory, `Vec<f32>` is a growable list.
pub struct PitchShifter {
    /// Circular buffer holding recent input samples.
    buffer: Vec<f32>,
    /// Where the next input sample will be written.
    write_pos: usize,
    /// Where we are inside the fade window, from 0.0 to 1.0.
    phase: f32,
    /// Length of the fade window, in samples.
    window: f32,
    /// How much `phase` moves per sample. Derived from the pitch ratio.
    phase_step: f32,
}

/// `impl` is where a type's functions (its "methods") live.
impl PitchShifter {
    /// Creates a shifter. `semitones` is how far to move the pitch:
    /// +12 is one octave up, -12 one octave down, 0 changes nothing.
    pub fn new(sample_rate: u32, semitones: f32, window_ms: f32) -> Self {
        // A semitone is a factor of 2^(1/12) in frequency.
        let ratio = 2f32.powf(semitones / 12.0);
        let window = (window_ms / 1000.0 * sample_rate as f32).max(32.0);
        // The buffer must be longer than the window, plus room for interpolation.
        let len = window as usize + 4;
        PitchShifter {
            buffer: vec![0.0; len],
            write_pos: 0,
            phase: 0.0,
            window,
            // If we read `ratio` samples per written sample, the delay
            // changes by (1 - ratio) samples each step.
            phase_step: (1.0 - ratio) / window,
        }
    }

    /// The average extra delay this effect adds, in milliseconds.
    /// Useful for the latency benchmark.
    pub fn algorithmic_latency_ms(&self, sample_rate: u32) -> f32 {
        self.window / 2.0 / sample_rate as f32 * 1000.0
    }

    /// Processes a block of samples in place. `&mut self` means "this
    /// function may change the shifter"; `&mut [f32]` means "a slice of
    /// samples we are allowed to overwrite".
    pub fn process(&mut self, samples: &mut [f32]) {
        for s in samples.iter_mut() {
            *s = self.process_sample(*s);
        }
    }

    /// Processes one sample. `#[inline]` hints the compiler to paste this
    /// code into the loop above instead of calling a function each time.
    #[inline]
    fn process_sample(&mut self, input: f32) -> f32 {
        let len = self.buffer.len();
        self.buffer[self.write_pos] = input;

        // Two heads, half a window apart. Each one's loudness follows a
        // smooth "hump" (sin²), and the two humps always add up to 1.0,
        // so the volume stays constant while we fade between them.
        let mut out = 0.0;
        for offset in [0.0, 0.5] {
            let p = (self.phase + offset).fract();
            let gain = (PI * p).sin().powi(2);
            let delay = p * self.window;
            out += gain * self.read_delayed(delay, len);
        }

        // Advance the phase and keep it between 0.0 and 1.0.
        self.phase = (self.phase + self.phase_step).rem_euclid(1.0);
        self.write_pos = (self.write_pos + 1) % len;
        out
    }

    /// Reads the sample from `delay` samples ago. The delay is usually not a
    /// whole number, so we blend the two nearest samples (linear interpolation).
    #[inline]
    fn read_delayed(&self, delay: f32, len: usize) -> f32 {
        let pos = self.write_pos as f32 - delay;
        let pos = if pos < 0.0 { pos + len as f32 } else { pos };
        let older = pos as usize % len; // the sample just before `pos`
        let newer = (older + 1) % len; // the sample just after `pos`
        let frac = pos - pos.floor(); // how far `pos` is from `older`, 0.0..1.0
        self.buffer[older] * (1.0 - frac) + self.buffer[newer] * frac
    }
}

// Tests live next to the code. `cargo test` runs every function marked `#[test]`.
#[cfg(test)]
mod tests {
    use super::*;
    use crate::testutil::{detect_pitch, sine};

    // Test tones are chosen so a whole number of cycles fits in the 30 ms
    // window. With other tones this simple shifter adds faint side tones
    // (heard as a slight "warble"), which would confuse the pitch detector.
    #[test]
    fn octave_up_doubles_frequency() {
        let sr = 48_000;
        let mut x = sine(200.0, sr, 1.0);
        PitchShifter::new(sr, 12.0, 30.0).process(&mut x);
        let f = detect_pitch(&x[4800..], sr);
        assert!((f - 400.0).abs() < 5.0, "got {f} Hz");
    }

    #[test]
    fn octave_down_halves_frequency() {
        let sr = 48_000;
        let mut x = sine(400.0, sr, 1.0);
        PitchShifter::new(sr, -12.0, 30.0).process(&mut x);
        let f = detect_pitch(&x[4800..], sr);
        assert!((f - 200.0).abs() < 5.0, "got {f} Hz");
    }
}

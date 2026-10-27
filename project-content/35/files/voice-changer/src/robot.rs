//! The robot voice: speech flattened to one fixed pitch, like a talking machine.
//!
//! How it works (in plain words):
//! A voice has two ingredients. The **pitch** is how fast the vocal cords
//! buzz (it rises and falls as you speak). The **vowel shape** is the
//! throat and mouth filtering that buzz (it is what makes "ah" differ from
//! "ee"). A robot keeps the second and replaces the first with a buzz at one
//! fixed frequency.
//!
//! We do that with the Fourier transform (FFT), which splits a short slice of
//! sound into its frequencies. For each frequency it gives a loudness and a
//! "phase" (where in its cycle the wave starts). The loudnesses describe the
//! vowel shape. The phases are what place the buzz pulses in time. So:
//!
//! 1. Every `hop` samples, take the last `size` samples and run the FFT.
//! 2. Keep every loudness, but set every phase to zero. With all phases
//!    equal, all the waves line up into one short pulse in the middle of the
//!    slice, shaped by the vowel.
//! 3. Run the FFT backwards to get that pulse, and add it to the output.
//!
//! One pulse per `hop` samples is a buzz at `sample_rate / hop` Hz, whatever
//! pitch you spoke at. That is the "frequency of the monotone".

use std::f32::consts::PI;

/// The range we accept for the monotone frequency.
pub const MIN_FREQ_HZ: f32 = 40.0;
pub const MAX_FREQ_HZ: f32 = 1000.0;

pub struct Robot {
    /// Samples between two pulses: `sample_rate / frequency`, rounded to a
    /// whole number (so the real frequency can be a fraction of a percent off).
    hop: usize,
    /// FFT length. A power of two, at least `2 * hop`, so slices overlap.
    size: usize,
    fft: Fft,
    /// Fades each slice in and out before the FFT (a Hann window).
    analysis: Vec<f32>,
    /// Fades each pulse out toward its edges, centred on index 0.
    synthesis: Vec<f32>,
    /// Scale that keeps the output about as loud as the input (see `new`).
    gain: f32,
    /// The last `size` input samples, as a circle.
    input: Vec<f32>,
    /// Pulses being added together ("overlap-add"), as a circle that lines
    /// up index for index with `input`.
    pulses: Vec<f32>,
    /// `hop` finished samples, played out one per input sample.
    ready: Vec<f32>,
    /// Where the next input sample goes. Also the oldest sample's index.
    pos: usize,
    /// How many samples we have taken in since the last pulse.
    since_hop: usize,
    /// Scratch space for the FFT, kept here so the audio thread never allocates.
    re: Vec<f32>,
    im: Vec<f32>,
}

impl Robot {
    /// `freq_hz` is the pitch of the monotone, between `MIN_FREQ_HZ` and `MAX_FREQ_HZ`.
    pub fn new(sample_rate: u32, freq_hz: f32) -> Self {
        let hop = ((sample_rate as f32 / freq_hz).round() as usize).max(1);
        let size = (2 * hop).next_power_of_two().max(256);

        let analysis: Vec<f32> = (0..size)
            .map(|i| 0.5 - 0.5 * (2.0 * PI * i as f32 / size as f32).cos())
            .collect();
        let synthesis: Vec<f32> = (0..size)
            .map(|i| 0.5 + 0.5 * (2.0 * PI * i as f32 / size as f32).cos())
            .collect();

        // The FFT keeps energy: a pulse holds as much as the slice it came
        // from, and a Hann-windowed slice holds 3/8 of `size` samples' worth.
        // One pulse is played per `hop` samples, so this scale brings the
        // average power back to the input's. The `1 / size` undoes the extra
        // factor our "backwards FFT" has (see `render_pulse`).
        let gain = (hop as f32 / (0.375 * size as f32)).sqrt() / size as f32;

        Robot {
            hop,
            size,
            fft: Fft::new(size),
            analysis,
            synthesis,
            gain,
            input: vec![0.0; size],
            pulses: vec![0.0; size],
            ready: vec![0.0; hop],
            pos: 0,
            since_hop: 0,
            re: vec![0.0; size],
            im: vec![0.0; size],
        }
    }

    /// The extra delay this effect adds, in milliseconds. A sample comes out
    /// `size` samples after it went in: we wait to see the whole slice
    /// around it, and the pulse can't be finished earlier.
    pub fn algorithmic_latency_ms(&self, sample_rate: u32) -> f32 {
        self.size as f32 / sample_rate as f32 * 1000.0
    }

    /// Processes a block of samples in place.
    pub fn process(&mut self, samples: &mut [f32]) {
        for s in samples.iter_mut() {
            *s = self.process_sample(*s);
        }
    }

    #[inline]
    fn process_sample(&mut self, input: f32) -> f32 {
        // Play the next finished sample first, then take the new one in.
        let out = self.ready[self.since_hop];
        self.input[self.pos] = input;
        self.pos = (self.pos + 1) & (self.size - 1);
        self.since_hop += 1;
        if self.since_hop == self.hop {
            self.since_hop = 0;
            self.render_pulse();
        }
        out
    }

    /// Turns the latest `size` input samples into one pulse, adds it to the
    /// output, and queues the next `hop` samples that are now complete.
    fn render_pulse(&mut self) {
        let size = self.size;
        let mask = size - 1;

        // 1. The last `size` samples, oldest first, faded at both ends.
        //    The oldest one sits at `pos`, because that's the next to be overwritten.
        let (newer, older) = self.input.split_at(self.pos);
        for (i, s) in older.iter().chain(newer).enumerate() {
            self.re[i] = s * self.analysis[i];
            self.im[i] = 0.0;
        }

        // 2. Keep each frequency's loudness and drop its phase. Bin 0 is the
        //    constant (DC) offset a microphone can add; as a pulse it would
        //    only be a hum at the monotone frequency, so we drop it too.
        self.fft.forward(&mut self.re, &mut self.im);
        for k in 0..size {
            self.re[k] = (self.re[k] * self.re[k] + self.im[k] * self.im[k]).sqrt();
            self.im[k] = 0.0;
        }
        self.re[0] = 0.0;

        // 3. Back to a waveform. The loudnesses mirror each other around the
        //    middle, so their inverse FFT is real, and equal to the forward
        //    FFT divided by `size`. We fold that division into `gain`, so one
        //    function does both directions. Index 0 is now the pulse's peak
        //    and the high indexes are its left half (it wraps around).
        self.fft.forward(&mut self.re, &mut self.im);

        // 4. Add the pulse into `pulses`, with its peak at the middle of the
        //    slice we just analysed, and fade its edges.
        let centre = (self.pos + size / 2) & mask;
        for k in 0..size {
            self.pulses[(centre + k) & mask] += self.re[k] * self.synthesis[k] * self.gain;
        }

        // 5. The oldest `hop` samples can't get any more pulses added (the
        //    next slice starts `hop` samples later). Queue them for playing
        //    and clear their slots for the samples that come next.
        for j in 0..self.hop {
            let slot = (self.pos + j) & mask;
            self.ready[j] = soft_limit(self.pulses[slot]);
            self.pulses[slot] = 0.0;
        }
    }
}

/// Keeps peaks under 1.0 without touching normal levels. Pulses are
/// spikier than speech (a peak can be over twice as high as the voice it came
/// from), and anything over 1.0 would crackle on the way to the speaker.
/// Up to `KNEE` the sample passes unchanged; above it, it bends smoothly
/// toward 1.0 with `tanh`, whose slope at 0 is 1, so there is no kink.
#[inline]
fn soft_limit(x: f32) -> f32 {
    const KNEE: f32 = 0.7;
    let over = x.abs() - KNEE;
    if over <= 0.0 {
        x
    } else {
        (KNEE + (1.0 - KNEE) * (over / (1.0 - KNEE)).tanh()).copysign(x)
    }
}

/// A basic Fast Fourier Transform (radix-2: the length must be a power of two).
///
/// It computes X[k] = sum over n of x[n] * e^(-2*pi*i*k*n/N) with about
/// N*log2(N) operations instead of N*N, by repeatedly combining pairs of
/// smaller transforms. Numbers are kept as separate real (`re`) and
/// imaginary (`im`) lists. The tables are made once so the audio thread does
/// no allocation and no `sin`/`cos` calls.
struct Fft {
    n: usize,
    /// For each index, the index with its bits in reverse order.
    bit_reversed: Vec<usize>,
    /// cos and sin of 2*pi*k/n, for k in 0..n/2.
    cos: Vec<f32>,
    sin: Vec<f32>,
}

impl Fft {
    fn new(n: usize) -> Self {
        assert!(n.is_power_of_two() && n >= 2);
        let bits = n.trailing_zeros();
        Fft {
            n,
            bit_reversed: (0..n)
                .map(|i| i.reverse_bits() >> (usize::BITS - bits))
                .collect(),
            cos: (0..n / 2)
                .map(|k| (2.0 * PI * k as f32 / n as f32).cos())
                .collect(),
            sin: (0..n / 2)
                .map(|k| (2.0 * PI * k as f32 / n as f32).sin())
                .collect(),
        }
    }

    fn forward(&self, re: &mut [f32], im: &mut [f32]) {
        let n = self.n;
        for i in 0..n {
            let j = self.bit_reversed[i];
            if i < j {
                re.swap(i, j);
                im.swap(i, j);
            }
        }
        // Combine transforms of length `len / 2` into transforms of length `len`.
        let mut len = 2;
        while len <= n {
            let half = len / 2;
            let step = n / len; // stride into the twiddle tables
            for start in (0..n).step_by(len) {
                for k in 0..half {
                    let (wr, wi) = (self.cos[k * step], -self.sin[k * step]);
                    let (a, b) = (start + k, start + k + half);
                    let tr = re[b] * wr - im[b] * wi;
                    let ti = re[b] * wi + im[b] * wr;
                    re[b] = re[a] - tr;
                    im[b] = im[a] - ti;
                    re[a] += tr;
                    im[a] += ti;
                }
            }
            len *= 2;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testutil::{detect_pitch, harmonic_voice, rms};

    #[test]
    fn fft_matches_the_slow_definition() {
        let n = 16;
        let x: Vec<f32> = (0..n).map(|i| ((i * i) as f32 * 0.37).sin()).collect();
        let (mut re, mut im) = (x.clone(), vec![0.0; n]);
        Fft::new(n).forward(&mut re, &mut im);
        for k in 0..n {
            let (mut sr, mut si) = (0.0f32, 0.0f32);
            for (i, v) in x.iter().enumerate() {
                let angle = -2.0 * PI * (k * i) as f32 / n as f32;
                sr += v * angle.cos();
                si += v * angle.sin();
            }
            assert!((re[k] - sr).abs() < 1e-4 && (im[k] - si).abs() < 1e-4, "bin {k}");
        }
    }

    // Whatever pitch goes in, the output buzzes at the chosen frequency.
    #[test]
    fn output_pitch_is_the_requested_frequency() {
        let sr = 48_000;
        for (spoken, wanted) in [(140.0, 100.0), (220.0, 100.0), (180.0, 150.0)] {
            let mut x = harmonic_voice(|_| spoken, sr, 1.0);
            Robot::new(sr, wanted).process(&mut x);
            let f = detect_pitch(&x[9600..], sr);
            assert!((f - wanted).abs() < 2.0, "spoke {spoken} Hz, got {f} Hz");
        }
    }

    // A wobbling voice (pitch gliding up and down) still comes out flat.
    #[test]
    fn gliding_input_pitch_comes_out_monotone() {
        let sr = 48_000;
        let mut x = harmonic_voice(|t| 140.0 + 60.0 * (2.0 * PI * 1.5 * t).sin(), sr, 2.0);
        Robot::new(sr, 120.0).process(&mut x);
        for part in x[9600..].chunks(24_000) {
            let f = detect_pitch(part, sr);
            assert!((f - 120.0).abs() < 2.0, "got {f} Hz");
        }
    }

    #[test]
    fn loud_input_never_clips() {
        let sr = 48_000;
        let mut x = harmonic_voice(|_| 150.0, sr, 1.0);
        x.iter_mut().for_each(|s| *s *= 3.0); // peaks around 1.0 going in
        Robot::new(sr, 100.0).process(&mut x);
        assert!(x.iter().all(|s| s.abs() <= 1.0));
    }

    #[test]
    fn soft_limit_leaves_normal_levels_alone() {
        assert_eq!(soft_limit(0.5), 0.5);
        assert_eq!(soft_limit(-0.7), -0.7);
        assert!((0.7..1.0).contains(&soft_limit(1.5)));
        assert!((-1.0..-0.7).contains(&soft_limit(-5.0)));
    }

    #[test]
    fn silence_stays_silent() {
        let mut x = vec![0.0; 10_000];
        Robot::new(48_000, 100.0).process(&mut x);
        assert!(x.iter().all(|&s| s == 0.0));
    }

    #[test]
    fn loudness_is_kept_roughly() {
        let sr = 48_000;
        let input = harmonic_voice(|_| 150.0, sr, 1.0);
        let mut out = input.clone();
        Robot::new(sr, 100.0).process(&mut out);
        let ratio = rms(&out[9600..]) / rms(&input[9600..]);
        assert!((0.7..1.4).contains(&ratio), "output is {ratio}x as loud");
    }

    // A tone burst should come out `algorithmic_latency_ms` later.
    #[test]
    fn delay_matches_the_reported_latency() {
        let sr = 48_000;
        let mut robot = Robot::new(sr, 100.0);
        let tone = harmonic_voice(|_| 150.0, sr, 0.5);
        let mut x = vec![0.0; 48_000];
        x[10_000..10_000 + tone.len()].copy_from_slice(&tone);
        let centre = |v: &[f32]| {
            let total: f32 = v.iter().map(|s| s * s).sum();
            v.iter().enumerate().map(|(i, s)| i as f32 * s * s).sum::<f32>() / total
        };
        let before = centre(&x);
        robot.process(&mut x);
        let delay_ms = (centre(&x) - before) / sr as f32 * 1000.0;
        let expected = robot.algorithmic_latency_ms(sr);
        assert!((delay_ms - expected).abs() < 3.0, "delay {delay_ms} ms, reported {expected} ms");
    }
}

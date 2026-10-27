//! The noise gate: silences the mic between words.
//!
//! It needs no setup and no "please be quiet" step. It keeps measuring the
//! mic's noise floor, the quietest the mic has been over the last few
//! seconds (everyone pauses between sentences), and only lets through what
//! is clearly louder than that. A new mic, or a new stream, starts the
//! measure over, so switching devices recalibrates by itself.
//!
//! Levels are peaks in dB, like the meters, so the numbers shown in the
//! window can be compared with them.
//!
//! Before the meter and the gate, `DcBlock` removes the constant offset
//! some mics add to their signal (the digital mics of AMD laptops on
//! Linux: one side sits at +0.26). It isn't sound, but it reads as a loud
//! noise floor, -17 dB on those mics, and the gate could never close under it.

/// Removes a constant offset: a high-pass filter at 20 Hz, below any voice.
pub struct DcBlock {
    r: f32,
    last_in: f32,
    last_out: f32,
}

impl DcBlock {
    pub fn new(rate: u32) -> DcBlock {
        DcBlock {
            r: (-std::f32::consts::TAU * 20.0 / rate as f32).exp(),
            last_in: 0.0,
            last_out: 0.0,
        }
    }

    pub fn process(&mut self, mono: &mut [f32]) {
        for s in mono.iter_mut() {
            let out = *s - self.last_in + self.r * self.last_out;
            self.last_in = *s;
            self.last_out = out;
            *s = out;
        }
    }
}

/// The level is measured over steps of this length.
const STEP_MS: u32 = 10;
/// The floor is the quietest moment of the last `SLOTS` × `SLOT_MS`.
const SLOTS: usize = 8;
const SLOT_MS: u32 = 500;
/// The gate stays open until this much has been measured.
const WARM_UP_MS: u32 = 1000;
/// Once open, the gate closes this much below where it opened, so a level
/// hovering around the threshold doesn't make it flutter.
const HYSTERESIS_DB: f32 = 3.0;
/// It stays open this long after the voice dropped, so word endings aren't cut.
const HOLD_MS: u32 = 250;
const ATTACK_MS: f32 = 2.0;
const RELEASE_MS: f32 = 120.0;
/// Below this, the mic sends (near) digital silence.
const SILENCE_DB: f32 = -96.0;

pub struct Gate {
    /// Samples per step.
    step: usize,
    /// The current step: its loudest sample, and how many samples it has.
    peak: f32,
    count: usize,
    /// The step levels smoothed over ~50 ms: the floor follows this, not
    /// single steps, which dip below the real noise now and then.
    smooth_db: Option<f32>,
    /// The quietest smoothed level of each recent slot, the current one last
    /// written at `slot`.
    mins: [f32; SLOTS],
    slot: usize,
    slot_steps: usize,
    steps_per_slot: usize,
    measured_steps: usize,
    warm_up_steps: usize,
    open: bool,
    /// Steps left before closing.
    hold: usize,
    hold_steps: usize,
    gain: f32,
    attack: f32,
    release: f32,
}

impl Gate {
    pub fn new(rate: u32) -> Gate {
        let per_ms = |ms: f32| (-1.0 / (ms * rate as f32 / 1000.0)).exp();
        Gate {
            step: (rate * STEP_MS / 1000).max(1) as usize,
            peak: 0.0,
            count: 0,
            smooth_db: None,
            mins: [f32::INFINITY; SLOTS],
            slot: 0,
            slot_steps: 0,
            steps_per_slot: (SLOT_MS / STEP_MS) as usize,
            measured_steps: 0,
            warm_up_steps: (WARM_UP_MS / STEP_MS) as usize,
            open: true,
            hold: 0,
            hold_steps: (HOLD_MS / STEP_MS) as usize,
            gain: 1.0,
            attack: per_ms(ATTACK_MS),
            release: per_ms(RELEASE_MS),
        }
    }

    /// The noise floor in dB, once enough has been measured.
    pub fn floor_db(&self) -> Option<f32> {
        if self.measured_steps < self.warm_up_steps {
            return None;
        }
        let min = self.mins.iter().copied().fold(f32::INFINITY, f32::min);
        min.is_finite().then_some(min.max(SILENCE_DB))
    }

    /// Measures `mono` and, when `enabled`, silences it while it is no
    /// louder than the floor plus `margin_db`. Disabled, it still measures.
    pub fn process(&mut self, mono: &mut [f32], enabled: bool, margin_db: f32) {
        for s in mono.iter_mut() {
            self.peak = self.peak.max(s.abs());
            self.count += 1;
            if self.count == self.step {
                self.end_step(margin_db);
            }
            let target = if self.open || !enabled { 1.0 } else { 0.0 };
            let coef = if target > self.gain {
                self.attack
            } else {
                self.release
            };
            self.gain = target + (self.gain - target) * coef;
            *s *= self.gain;
        }
    }

    fn end_step(&mut self, margin_db: f32) {
        let level = to_db(self.peak);
        self.peak = 0.0;
        self.count = 0;

        let smooth = match self.smooth_db {
            Some(s) => s + (level - s) * 0.2,
            None => level,
        };
        self.smooth_db = Some(smooth);
        self.mins[self.slot] = self.mins[self.slot].min(smooth);
        self.slot_steps += 1;
        if self.slot_steps == self.steps_per_slot {
            self.slot_steps = 0;
            self.slot = (self.slot + 1) % SLOTS;
            self.mins[self.slot] = f32::INFINITY;
        }
        self.measured_steps = self.measured_steps.saturating_add(1);

        let Some(floor) = self.floor_db() else {
            self.open = true;
            return;
        };
        let opens_at = floor + margin_db;
        if level > opens_at {
            self.open = true;
            self.hold = self.hold_steps;
        } else if self.open && level > opens_at - HYSTERESIS_DB {
            self.hold = self.hold_steps;
        } else if self.hold > 0 {
            self.hold -= 1;
        } else {
            self.open = false;
        }
    }
}

fn to_db(peak: f32) -> f32 {
    if peak > 1e-6 {
        20.0 * peak.log10()
    } else {
        SILENCE_DB - 24.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const RATE: u32 = 48_000;

    /// `ms` of a steady tone at `peak`: what a hissing mic or a voice looks like to the gate.
    fn tone(peak: f32, ms: u32) -> Vec<f32> {
        let n = (RATE * ms / 1000) as usize;
        (0..n)
            .map(|i| peak * (i as f32 * 0.07).sin().signum())
            .collect()
    }

    fn loudest(block: &[f32]) -> f32 {
        block.iter().fold(0.0, |m, s| m.max(s.abs()))
    }

    #[test]
    fn learns_the_floor_without_asking_for_silence() {
        let mut gate = Gate::new(RATE);
        // A noisy mic: -17 dB of hiss.
        let mut noise = tone(0.141, 400);
        gate.process(&mut noise, true, 9.0);
        assert_eq!(gate.floor_db(), None, "still measuring");
        assert!(loudest(&noise) > 0.1, "open while measuring");
        for _ in 0..4 {
            let mut noise = tone(0.141, 400);
            gate.process(&mut noise, true, 9.0);
        }
        let floor = gate.floor_db().unwrap();
        assert!((floor + 17.0).abs() < 0.5, "floor {floor}");
        let mut noise = tone(0.141, 400);
        gate.process(&mut noise, true, 9.0);
        assert!(
            loudest(&noise[noise.len() / 2..]) < 0.01,
            "the hiss is gated"
        );
    }

    #[test]
    fn a_voice_opens_it_and_the_hold_keeps_word_endings() {
        let mut gate = Gate::new(RATE);
        for _ in 0..5 {
            gate.process(&mut tone(0.01, 400), true, 9.0);
        }
        let mut voice = tone(0.5, 100);
        gate.process(&mut voice, true, 9.0);
        assert!(
            loudest(&voice[voice.len() / 2..]) > 0.45,
            "open for the voice"
        );
        // Right after the voice: still open (hold), then closed.
        let mut after = tone(0.01, 150);
        gate.process(&mut after, true, 9.0);
        assert!(loudest(&after) > 0.009);
        let mut later = tone(0.01, 600);
        gate.process(&mut later, true, 9.0);
        assert!(loudest(&later[later.len() * 3 / 4..]) < 0.001);
    }

    #[test]
    fn talking_for_a_while_doesnt_raise_the_floor_and_a_new_noise_is_learned() {
        let mut gate = Gate::new(RATE);
        gate.process(&mut tone(0.01, 2000), true, 9.0);
        // Five seconds of talking with short pauses.
        for _ in 0..10 {
            gate.process(&mut tone(0.5, 400), true, 9.0);
            gate.process(&mut tone(0.01, 100), true, 9.0);
        }
        assert!(gate.floor_db().unwrap() < -35.0);
        // A fan starts: within a few seconds it is the new floor.
        gate.process(&mut tone(0.05, 5000), true, 9.0);
        let floor = gate.floor_db().unwrap();
        assert!((floor - to_db(0.05)).abs() < 0.5, "floor {floor}");
    }

    #[test]
    fn the_offset_goes_and_the_voice_stays() {
        let mut dc = DcBlock::new(RATE);
        // An offset of 0.14 (-17 dB) with quiet hiss on top, then a voice.
        let mut quiet: Vec<f32> = tone(0.01, 1000).iter().map(|s| s + 0.14).collect();
        dc.process(&mut quiet);
        assert!(loudest(&quiet[quiet.len() / 2..]) < 0.012);
        let mut voice: Vec<f32> = tone(0.5, 200).iter().map(|s| s + 0.14).collect();
        dc.process(&mut voice);
        assert!(loudest(&voice[voice.len() / 2..]) > 0.45);
    }

    #[test]
    fn disabled_it_only_measures() {
        let mut gate = Gate::new(RATE);
        gate.process(&mut tone(0.01, 2000), false, 9.0);
        let mut quiet = tone(0.01, 200);
        gate.process(&mut quiet, false, 9.0);
        assert!(loudest(&quiet) > 0.009);
        assert!(gate.floor_db().is_some());
    }
}

//! Auto-click timing, ported from Valkyrie's `autoclick.py` with its tests.
//!
//! No input or output here: times are seconds given by the caller, so the
//! tests can use a fake clock. Clicks are placed on a fixed grid counted from
//! the first one, so the rate never drifts, and a late wake-up skips the
//! clicks it missed instead of sending them all at once.

use crate::config::{AutoClick, ClickMode, MouseButton};

/// Something to send to the virtual mouse.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Out {
    Button(MouseButton, bool),
    /// Horizontal move, in pixels (negative: left).
    Move(i32),
}

pub struct Clicker {
    pub button: MouseButton,
    pub mode: ClickMode,
    pub rate: f32,
    max_rate: f32,
    press_ms: Option<f32>,
    /// Seconds between clicks, and how long each one holds the button.
    period: f64,
    press: f64,
    /// Clicking now.
    pub active: bool,
    /// Our button is pressed.
    down: bool,
    pressed_at: f64,
    /// When the grid starts, and the clicks started since.
    start: f64,
    count: u64,
}

impl Clicker {
    pub fn new(settings: &AutoClick) -> Clicker {
        let mut clicker = Clicker {
            button: settings.button,
            mode: settings.mode,
            rate: 1.0,
            max_rate: 1.0,
            press_ms: None,
            period: 1.0,
            press: 0.0,
            active: false,
            down: false,
            pressed_at: 0.0,
            start: 0.0,
            count: 0,
        };
        clicker.configure(settings);
        clicker
    }

    /// New settings, while running. Rate and press length change from the
    /// next click; a new button or mode stops clicking. -> events to send.
    pub fn configure(&mut self, settings: &AutoClick) -> Vec<Out> {
        let mut out = Vec::new();
        if settings.button != self.button || settings.mode != self.mode {
            out = self.stop();
            self.button = settings.button;
            self.mode = settings.mode;
        }
        self.max_rate = settings.max_rate.max(1.0);
        self.press_ms = settings.press_ms;
        if settings.rate != self.rate {
            self.set_rate(settings.rate);
        } else {
            self.set_timing();
        }
        out
    }

    /// The trigger key went down or up (not repeats).
    /// -> Some(true) if clicking started, Some(false) if it stopped.
    pub fn key(&mut self, pressed: bool, now: f64) -> Option<bool> {
        let was = self.active;
        match self.mode {
            ClickMode::Hold if pressed && !self.active => self.begin(now),
            ClickMode::Hold if !pressed => self.active = false,
            ClickMode::Toggle if pressed && self.active => self.active = false,
            ClickMode::Toggle if pressed => self.begin(now),
            _ => {}
        }
        (self.active != was).then_some(self.active)
    }

    /// A new rate, clamped to 1..=max_rate, effective from the next click
    /// (clicking goes on). -> the rate now used.
    pub fn set_rate(&mut self, rate: f32) -> f32 {
        self.rate = rate.clamp(1.0, self.max_rate);
        self.set_timing();
        if self.active && self.count > 0 {
            // Re-anchor the grid on the last click: the next one comes one new period after it.
            self.start = self.pressed_at;
            self.count = 1;
        }
        self.rate
    }

    fn set_timing(&mut self) {
        self.rate = self.rate.clamp(1.0, self.max_rate);
        self.period = 1.0 / self.rate as f64;
        // A press never lasts more than half the period, so clicks stay clicks.
        let press = self.press_ms.map_or(0.020, |ms| ms as f64 / 1000.0);
        self.press = press.min(self.period / 2.0);
    }

    /// Hold <-> toggle. -> (the new mode, events that leave the button released, true if clicking stopped).
    pub fn switch_mode(&mut self) -> (ClickMode, Vec<Out>, bool) {
        let stopped = self.active;
        let out = self.stop();
        self.mode = match self.mode {
            ClickMode::Hold => ClickMode::Toggle,
            ClickMode::Toggle => ClickMode::Hold,
        };
        (self.mode, out, stopped)
    }

    fn begin(&mut self, now: f64) {
        self.active = true;
        self.start = now;
        self.count = 0;
    }

    fn next_press(&self) -> f64 {
        self.start + self.count as f64 * self.period
    }

    /// When `due` has something to do next, if ever.
    pub fn deadline(&self) -> Option<f64> {
        if self.down {
            Some(self.pressed_at + self.press)
        } else if self.active {
            Some(self.next_press())
        } else {
            None
        }
    }

    /// The events to send at `now`.
    pub fn due(&mut self, now: f64) -> Vec<Out> {
        let mut out = Vec::new();
        if self.down && now >= self.pressed_at + self.press {
            out.push(Out::Button(self.button, false));
            self.down = false;
        }
        if self.active && !self.down && now >= self.next_press() {
            // Skip the clicks we are too late for.
            let missed = ((now - self.next_press()) / self.period) as u64;
            self.count += missed + 1;
            out.push(Out::Button(self.button, true));
            self.down = true;
            self.pressed_at = now;
        }
        out
    }

    /// Stops clicking. -> events that leave the button released.
    pub fn stop(&mut self) -> Vec<Out> {
        self.active = false;
        if self.down {
            self.down = false;
            vec![Out::Button(self.button, false)]
        } else {
            Vec::new()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const LEFT: MouseButton = MouseButton::Left;

    fn clicker(rate: f32, mode: ClickMode) -> Clicker {
        Clicker::new(&AutoClick {
            rate,
            mode,
            max_rate: 100.0,
            ..AutoClick::default()
        })
    }

    /// Runs a 1 ms fake clock. presses: (time, key down). -> (time, button down) sent.
    fn simulate(c: &mut Clicker, presses: &[(f64, bool)], until: f64) -> Vec<(f64, bool)> {
        let mut sent = Vec::new();
        for ms in 0..=(until * 1000.0).round() as u64 {
            // A hair late, like a real clock: 3 × 0.1 is a bit more than 0.3 in floats.
            let t = ms as f64 / 1000.0 + 1e-9;
            for &(when, down) in presses {
                if (when - t).abs() < 0.0005 {
                    c.key(down, when);
                }
            }
            for out in c.due(t) {
                if let Out::Button(_, down) = out {
                    sent.push(((t * 1000.0).round() / 1000.0, down));
                }
            }
        }
        sent
    }

    fn presses(sent: &[(f64, bool)]) -> Vec<f64> {
        sent.iter().filter(|(_, d)| *d).map(|(t, _)| *t).collect()
    }

    #[test]
    fn hold_clicks_at_the_rate_while_held() {
        let sent = simulate(
            &mut clicker(10.0, ClickMode::Hold),
            &[(0.0, true), (0.35, false)],
            1.0,
        );
        assert_eq!(presses(&sent), [0.0, 0.1, 0.2, 0.3]);
        assert_eq!(sent.iter().filter(|(_, d)| !d).count(), 4); // every press released
        assert_eq!(sent[1], (0.02, false)); // held 20 ms
    }

    #[test]
    fn toggle_starts_and_stops_on_presses() {
        let mut c = clicker(20.0, ClickMode::Toggle);
        let sent = simulate(
            &mut c,
            &[(0.0, true), (0.01, false), (0.5, true), (0.51, false)],
            1.0,
        );
        assert_eq!(presses(&sent).len(), 10); // 0.00 .. 0.45
        assert!(!sent.last().unwrap().1);
    }

    #[test]
    fn press_time_is_half_the_period_when_fast() {
        let sent = simulate(&mut clicker(50.0, ClickMode::Hold), &[(0.0, true)], 0.05);
        assert_eq!(sent[..2], [(0.0, true), (0.01, false)]);
    }

    #[test]
    fn stop_releases_the_button() {
        let mut c = clicker(10.0, ClickMode::Hold);
        c.key(true, 0.0);
        c.due(0.0);
        assert_eq!(c.stop(), [Out::Button(LEFT, false)]);
        assert_eq!(c.deadline(), None);
    }

    #[test]
    fn key_reports_start_and_stop() {
        let mut c = clicker(10.0, ClickMode::Toggle);
        let changes = [
            c.key(true, 0.0),
            c.key(false, 0.1),
            c.key(true, 0.5),
            c.key(false, 0.6),
        ];
        assert_eq!(changes, [Some(true), None, Some(false), None]);
        let mut c = clicker(10.0, ClickMode::Hold);
        assert_eq!(
            [c.key(true, 0.0), c.key(false, 0.1)],
            [Some(true), Some(false)]
        );
    }

    #[test]
    fn faster_while_clicking_keeps_going_at_the_new_rate() {
        let mut c = clicker(10.0, ClickMode::Toggle);
        c.key(true, 0.0);
        c.due(0.0); // click at 0.0
        c.due(0.02); // released
        assert_eq!(c.set_rate(20.0), 20.0);
        assert!((c.next_press() - 0.05).abs() < 1e-9); // one new period after the last click
        assert!((c.press - 0.020).abs() < 1e-9);
        assert_eq!(c.set_rate(500.0), 100.0);
        assert_eq!(c.set_rate(-3.0), 1.0);
    }

    #[test]
    fn rate_stops_at_max_rate() {
        let mut c = Clicker::new(&AutoClick::default());
        assert_eq!(c.set_rate(21.0), 20.0);
    }

    #[test]
    fn press_time_shrinks_with_the_period() {
        let mut c = Clicker::new(&AutoClick {
            rate: 10.0,
            press_ms: Some(40.0),
            max_rate: 100.0,
            ..AutoClick::default()
        });
        assert!((c.press - 0.040).abs() < 1e-9);
        c.set_rate(50.0);
        assert!((c.press - 0.010).abs() < 1e-9); // half of 20 ms
    }

    #[test]
    fn switch_mode_stops_clicking() {
        let mut c = clicker(10.0, ClickMode::Toggle);
        c.key(true, 0.0);
        let (mode, _, stopped) = c.switch_mode();
        assert_eq!((mode, stopped), (ClickMode::Hold, true));
        assert!(!c.active);
        let (mode, _, stopped) = c.switch_mode();
        assert_eq!((mode, stopped), (ClickMode::Toggle, false));
    }

    #[test]
    fn late_wakeup_skips_missed_clicks() {
        let mut c = clicker(10.0, ClickMode::Hold);
        c.key(true, 0.0);
        c.due(0.0);
        c.due(0.02);
        assert_eq!(c.due(0.55), [Out::Button(LEFT, true)]); // one click, not five
        assert!((c.next_press() - 0.6).abs() < 1e-9);
    }

    #[test]
    fn a_new_button_releases_the_old_one() {
        let mut c = clicker(10.0, ClickMode::Hold);
        c.key(true, 0.0);
        c.due(0.0);
        let right = AutoClick {
            button: MouseButton::Right,
            mode: ClickMode::Hold,
            rate: 10.0,
            max_rate: 100.0,
            ..AutoClick::default()
        };
        assert_eq!(c.configure(&right), [Out::Button(LEFT, false)]);
        assert!(!c.active);
    }
}

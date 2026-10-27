//! Mouse drift, from the .NET app: ← or → starts moving the mouse that way
//! (15 px every 20 ms by default), the same key stops it, the other key
//! switches direction. Like the clicker, it takes times from the caller.

use super::clicker::Out;
use crate::config::Drift;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Direction {
    Left,
    Right,
}

pub struct Drifter {
    px: i32,
    every: f64,
    pub direction: Option<Direction>,
    next: f64,
}

impl Drifter {
    pub fn new(settings: &Drift) -> Drifter {
        let mut drifter = Drifter {
            px: 0,
            every: 1.0,
            direction: None,
            next: 0.0,
        };
        drifter.configure(settings);
        drifter
    }

    pub fn configure(&mut self, settings: &Drift) {
        self.px = settings.px.max(1);
        self.every = settings.every_ms.max(1) as f64 / 1000.0;
    }

    /// A drift key was pressed: start, stop or switch.
    pub fn key(&mut self, direction: Direction, now: f64) {
        if self.direction == Some(direction) {
            self.direction = None;
        } else {
            self.direction = Some(direction);
            self.next = now;
        }
    }

    pub fn stop(&mut self) {
        self.direction = None;
    }

    pub fn deadline(&self) -> Option<f64> {
        self.direction.map(|_| self.next)
    }

    /// The move to make at `now`, if one is due.
    pub fn due(&mut self, now: f64) -> Option<Out> {
        let direction = self.direction?;
        if now < self.next {
            return None;
        }
        // One step per wake-up: after a late one, go on from now instead of catching up.
        self.next += self.every;
        if self.next <= now {
            self.next = now + self.every;
        }
        Some(Out::Move(match direction {
            Direction::Left => -self.px,
            Direction::Right => self.px,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_key_stops_and_other_key_switches() {
        let mut d = Drifter::new(&Drift::default());
        d.key(Direction::Left, 0.0);
        assert_eq!(d.due(0.0), Some(Out::Move(-15)));
        assert_eq!(d.due(0.01), None);
        assert_eq!(d.due(0.02), Some(Out::Move(-15)));
        d.key(Direction::Right, 0.03);
        assert_eq!(d.due(0.03), Some(Out::Move(15)));
        d.key(Direction::Right, 0.04);
        assert_eq!((d.due(1.0), d.deadline()), (None, None));
    }

    #[test]
    fn a_late_wakeup_moves_once() {
        let mut d = Drifter::new(&Drift::default());
        d.key(Direction::Right, 0.0);
        d.due(0.0);
        assert_eq!(d.due(0.5), Some(Out::Move(15)));
        assert_eq!(d.due(0.5), None);
        assert!((d.deadline().unwrap() - 0.52).abs() < 1e-9);
    }
}

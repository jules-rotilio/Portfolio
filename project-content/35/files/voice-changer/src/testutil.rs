//! Helpers shared by the tests of several effects. Only compiled for `cargo test`.

use std::f32::consts::PI;

/// Estimates the main frequency of a signal by finding the delay at which
/// it best matches itself (autocorrelation): a simple pitch detector.
/// A tone also matches itself after 2, 3... periods, so we take the
/// shortest delay that is a peak almost as good as the best one.
pub fn detect_pitch(x: &[f32], sr: u32) -> f32 {
    let n = 2048;
    let (min_lag, max_lag) = (sr as usize / 1000, sr as usize / 80);
    let mut periods = Vec::new();
    for start in (0..x.len() - n - max_lag).step_by(n) {
        let corr = |lag: usize| -> f32 { (0..n).map(|i| x[start + i] * x[start + i + lag]).sum() };
        let scores: Vec<f32> = (min_lag..max_lag).map(corr).collect();
        let top = scores.iter().cloned().fold(f32::MIN, f32::max);
        let best = min_lag
            + (1..scores.len() - 1)
                .find(|&i| {
                    let c = scores[i];
                    c >= 0.9 * top && c >= scores[i - 1] && c >= scores[i + 1]
                })
                .unwrap();
        periods.push(best as f32);
    }
    periods.sort_by(|a, b| a.total_cmp(b));
    sr as f32 / periods[periods.len() / 2]
}

/// Root mean square: the typical size of the samples, a measure of loudness.
pub fn rms(x: &[f32]) -> f32 {
    (x.iter().map(|s| s * s).sum::<f32>() / x.len() as f32).sqrt()
}

pub fn sine(freq: f32, sr: u32, seconds: f32) -> Vec<f32> {
    let n = (sr as f32 * seconds) as usize;
    (0..n)
        .map(|i| (2.0 * PI * freq * i as f32 / sr as f32).sin())
        .collect()
}

/// A buzzy voice-like signal (the first 10 harmonics of a changing pitch).
/// `f0` gives the pitch in Hz at time `t` seconds.
pub fn harmonic_voice(f0: impl Fn(f32) -> f32, sr: u32, seconds: f32) -> Vec<f32> {
    let n = (sr as f32 * seconds) as usize;
    let mut phase = 0.0f32;
    (0..n)
        .map(|i| {
            phase = (phase + f0(i as f32 / sr as f32) / sr as f32).fract();
            let s: f32 = (1..=10)
                .map(|h| (2.0 * PI * phase * h as f32).sin() / h as f32)
                .sum();
            0.3 * s
        })
        .collect()
}

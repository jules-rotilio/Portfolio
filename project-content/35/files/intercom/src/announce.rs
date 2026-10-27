//! Spoken confirmations when the voice changer is turned on or off, heard in
//! your headset only (like the auto-click chimes).
//!
//! The two built-in lines were made once with the Piper text-to-speech
//! engine (voice "en_US-joe", public domain) and are built into the program,
//! so nothing needs to be installed. Your own sound files can replace them.
//! The "on" line can be spoken in the new voice, so you hear what others will.

use crate::audio::Player;
use crate::config::VoiceConfig;
use std::io::Cursor;
use voice_changer::audio_file::{read_audio, resample};
use voice_changer::effect::Effect;

const VOICE_ON: &[u8] = include_bytes!("../assets/voice-on.wav");
const VOICE_OFF: &[u8] = include_bytes!("../assets/voice-off.wav");

/// A 16-bit WAV built into the program -> (samples, sample rate).
fn decode(wav: &[u8]) -> (Vec<f32>, u32) {
    let mut reader = hound::WavReader::new(Cursor::new(wav)).expect("built-in WAV");
    let rate = reader.spec().sample_rate;
    let samples = reader
        .samples::<i16>()
        .map(|s| s.unwrap_or(0) as f32 / 32768.0)
        .collect();
    (samples, rate)
}

/// The line for `on`: your own file if one is set and readable, else the built-in one.
fn line(voice: &VoiceConfig, on: bool) -> (Vec<f32>, u32) {
    let custom = if on {
        &voice.announce_on
    } else {
        &voice.announce_off
    };
    if let Some(path) = custom
        && let Ok(clip) = read_audio(path)
    {
        return clip;
    }
    decode(if on { VOICE_ON } else { VOICE_OFF })
}

/// Says "Voice changer on" or "off" in the headset, if turned on in the settings.
pub fn announce(player: &Player, voice: &VoiceConfig, on: bool) {
    if !voice.announce {
        return;
    }
    let (mut samples, rate) = line(voice, on);
    if on && voice.announce_in_effect {
        Effect::new(&voice.effect_args(), rate).process(&mut samples);
    }
    player.cue(|to| resample(&samples, rate, to), voice.announce_volume);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn built_in_lines_decode() {
        for wav in [VOICE_ON, VOICE_OFF] {
            let (samples, rate) = decode(wav);
            assert_eq!(rate, 22_050);
            let seconds = samples.len() as f32 / rate as f32;
            assert!((0.8..1.5).contains(&seconds), "{seconds} s");
            assert!(samples.iter().any(|s| s.abs() > 0.5));
        }
    }
}

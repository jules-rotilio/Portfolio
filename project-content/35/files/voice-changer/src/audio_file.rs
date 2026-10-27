//! Audio files: reading any common format, and changing the sample rate.

use std::path::Path;
use symphonia::core::errors::Error as DecodeFailure;
use symphonia::core::formats::TrackType;
use symphonia::core::formats::probe::Hint;
use symphonia::core::io::MediaSourceStream;

/// Reads an audio file in any format the symphonia library knows (WAV, MP3,
/// FLAC, OGG...) and mixes it down to mono, the same way the live mode does.
/// Returns the samples, as decimal numbers between -1.0 and 1.0, and their
/// sample rate.
///
/// A compressed file like an MP3 is a series of "packets", each holding a few
/// milliseconds of sound. We unpack ("decode") them one at a time.
pub fn read_audio(path: &Path) -> Result<(Vec<f32>, u32), Box<dyn std::error::Error>> {
    let file =
        std::fs::File::open(path).map_err(|e| format!("can't open {}: {e}", path.display()))?;
    let stream = MediaSourceStream::new(Box::new(file), Default::default());
    // The extension helps symphonia guess the format; it checks the contents too.
    let mut hint = Hint::new();
    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
        hint.with_extension(ext);
    }
    let mut format = symphonia::default::get_probe().probe(
        &hint,
        stream,
        Default::default(),
        Default::default(),
    )?;
    let track = format
        .default_track(TrackType::Audio)
        .ok_or("the file has no audio in it")?;
    let track_id = track.id;
    let params = track
        .codec_params
        .as_ref()
        .and_then(|p| p.audio())
        .ok_or("unknown audio format")?;
    let mut sample_rate = params.sample_rate;
    let mut decoder =
        symphonia::default::get_codecs().make_audio_decoder(params, &Default::default())?;

    let mut mono = Vec::new();
    let mut interleaved: Vec<f32> = Vec::new();
    while let Some(packet) = format.next_packet()? {
        // A file can hold several tracks (a video's sound and pictures, say).
        if packet.track_id != track_id {
            continue;
        }
        let decoded = match decoder.decode(&packet) {
            Ok(decoded) => decoded,
            // A damaged packet: skip those few milliseconds, like music players do.
            Err(DecodeFailure::DecodeError(_) | DecodeFailure::IoError(_)) => continue,
            Err(e) => return Err(e.into()),
        };
        sample_rate = Some(decoded.spec().rate());
        let channels = decoded.num_planes();
        interleaved.resize(decoded.samples_interleaved(), 0.0);
        decoded.copy_to_slice_interleaved(&mut interleaved);
        mono.extend(
            interleaved
                .chunks(channels)
                .map(|frame| frame.iter().sum::<f32>() / channels as f32),
        );
    }
    Ok((mono, sample_rate.ok_or("unknown sample rate")?))
}

/// Changes the sample rate of `samples` from `from` to `to` Hz, by drawing
/// straight lines between the samples (linear interpolation). It's the
/// simplest method, and good enough for listening.
pub fn resample(samples: &[f32], from: u32, to: u32) -> Vec<f32> {
    let step = from as f64 / to as f64; // how far we move in `samples` per new sample
    let len = (samples.len() as f64 / step) as usize;
    (0..len)
        .map(|i| {
            let pos = i as f64 * step;
            let older = pos as usize; // the sample just before `pos`
            let newer = (older + 1).min(samples.len() - 1); // the sample just after
            let frac = (pos - older as f64) as f32; // how far `pos` is from `older`
            samples[older] * (1.0 - frac) + samples[newer] * frac
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testutil::{detect_pitch, sine};

    // Converting the rate must not change the pitch or the length in seconds.
    #[test]
    fn resample_keeps_pitch_and_duration() {
        let x = sine(440.0, 44_100, 1.0);
        let y = resample(&x, 44_100, 48_000);
        assert!(y.len().abs_diff(48_000) <= 1, "{} samples", y.len());
        let f = detect_pitch(&y, 48_000);
        assert!((f - 440.0).abs() < 5.0, "got {f} Hz");
    }
}

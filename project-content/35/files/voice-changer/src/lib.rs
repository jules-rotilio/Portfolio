//! The voice changer as a library: the effects, and the audio plumbing
//! around them. The `voice-changer` program (`src/main.rs`) is built on it,
//! and other programs (like Intercom) can use it too.
//!
//! `pub mod x;` makes the file `src/x.rs` part of the library, and `pub`
//! lets the programs that use it see it.
pub mod audio_file;
pub mod devices;
pub mod effect;
pub mod pitch;
pub mod retro;
pub mod robot;
#[cfg(test)]
mod testutil;

/// "Any kind of error": for functions that can fail in several different
/// ways (file not found, bad MP3, no sound card...).
pub type AnyResult<T> = Result<T, Box<dyn std::error::Error>>;

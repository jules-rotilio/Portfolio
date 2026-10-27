//! Real-time voice changer. Start reading here.
//!
//! The effects and the sound-card code are a library (`src/lib.rs`), so
//! other programs can use them too. This file and the three below are the
//! command-line program around it.
//!
//! `mod x;` tells Rust that the file `src/x.rs` is part of this program.
mod live;
mod offline;
mod results;

use clap::{Parser, Subcommand};

/// The `#[derive(Parser)]` line asks the clap library to turn this struct into
/// a command-line parser. The `///` comments become the `--help` text.
#[derive(Parser)]
#[command(
    version,
    about = "Real-time voice changer: pitch shift, robot and retro console voices"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

/// An `enum` is a type that is exactly one of several variants. Here, each
/// variant is one sub-command, e.g. `voice-changer live --pitch 5`. Each
/// sub-command's options are a struct kept next to the code that uses them:
/// `LiveOptions` in live.rs, `BenchOptions` and `FileOptions` in offline.rs.
#[derive(Subcommand)]
enum Command {
    /// Change your voice live: microphone in, speakers (or a virtual cable) out
    Live(live::LiveOptions),
    /// Measure processing speed without any audio device
    Bench(offline::BenchOptions),
    /// Apply the effect to an audio file (WAV, MP3, FLAC, OGG...) and save or play the result
    File(offline::FileOptions),
    /// List microphones and outputs
    Devices,
}

/// `main` is where every Rust program starts.
fn main() {
    let cli = Cli::parse();

    // `match` runs the branch that fits the sub-command the user typed.
    // Each branch returns a Result; on error we print it and exit with code 1.
    let result: Result<(), Box<dyn std::error::Error>> = match cli.command {
        Command::Live(opts) => live::run(&opts),
        Command::Bench(opts) => offline::bench(&opts).map_err(Into::into),
        Command::File(opts) => offline::process_file(&opts),
        Command::Devices => live::list_devices(),
    };

    if let Err(e) = result {
        eprintln!("Error: {e}");
        std::process::exit(1);
    }
}

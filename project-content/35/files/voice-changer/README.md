# Voice changer (Rust), explained from zero

This program listens to your microphone, changes your voice with an effect (raise or lower the
pitch, turn it into a monotone robot, or make it sound like an old games console), and plays it back
(to your headphones, or into a virtual microphone so other apps hear the new voice). It can also
change a recording (WAV, MP3...) and play or save the result. It measures how much delay it adds and how much CPU it uses, and saves those numbers so we can
compare it with the two Python apps later.

You don't need to know any Rust to use it. Part 1 gets it running. Parts 2 to 4 explain how it
works and what every piece of Rust in it means, so you can read the code and change it.

---

## Part 1: Install, build, run

### 1.1 Install Rust

Rust comes with a tool called **rustup** that installs everything for you:

- **rustc**: the compiler. It turns the `.rs` source files into a program your computer can run.
- **cargo**: the helper you'll actually type. It downloads libraries, calls the compiler, runs tests.

On Linux, first install a C linker and the sound library headers. The program talks to the
sound card through ALSA, which PipeWire and PulseAudio also understand, so this works on any
modern desktop:

```
# Ubuntu, Debian, Mint, Pop!_OS
sudo apt install build-essential pkg-config libasound2-dev
# Fedora
sudo dnf install gcc pkgconf-pkg-config alsa-lib-devel
# Arch
sudo pacman -S base-devel alsa-lib
```

Then install Rust itself (it asks a question: press Enter for the default):

```
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

(On macOS it's the same line after `xcode-select --install`. On Windows, run `rustup-init.exe`
from <https://rustup.rs>.)

Close and reopen your terminal, then check it worked:

```
cargo --version
```

### 1.2 Build and run

Open a terminal in the `voice-changer` folder (the one with `Cargo.toml` in it).

```
cargo build --release
```

The first build downloads the libraries and takes a minute or two; later builds take seconds.
`--release` turns on all optimisations. **Always use it for this app**: without it the code
can be 10 to 50 times slower, which would ruin the benchmark.

Then, **with headphones on** (otherwise the speaker feeds back into the mic and howls):

```
cargo run --release -- live
```

Everything after the lone `--` is passed to our program rather than to cargo. Press Enter to stop.
You'll see a line every second like:

```
latency ≈  27.4 ms (input 5.3 + queue 2.1 + output 5.0 + effect 15.0) | processing 9.8 us/block | underruns 0
```

### 1.3 All the commands

| Command | What it does |
|---|---|
| `cargo run --release -- live` | Live voice change, default +5 semitones. |
| `cargo run --release -- live --pitch -4` | Deeper voice. `+12` is one octave up, `-12` one octave down. |
| `cargo run --release -- live --window-ms 20` | Less delay, slightly rougher sound. `40` is smoother but slower. |
| `cargo run --release -- live --effect robot` | Robot voice: everything you say comes out on one fixed note (100 Hz by default). |
| `cargo run --release -- live --effect robot --freq 180` | Choose that note in Hz. Lower is deeper and a little slower to respond; higher sounds smaller and more squeaky. Allowed: 40 to 1000. |
| `cargo run --release -- live --effect 8bit` | Your voice as a dull, buzzy 8-bit console voice clip (NES, Game Boy era). |
| `cargo run --release -- live --effect 16bit` | Softer and a little muffled, like a 16-bit console (SNES, Mega Drive era). |
| `cargo run --release -- live --effect 4bit` | Even worse than `8bit`: a muffled, whistly voice, like a cheap talking toy. |
| `cargo run --release -- live --effect 8bit --bits 4` | Add grit: fewer `--bits` (1 to 16, default 16) is grittier. 4 is about what 8-bit consoles had, 8 what 16-bit ones had. |
| `cargo run --release -- live --effect 8bit --rate 6000` | A lower `--rate` (1000 to 48000 Hz) is duller, with more metallic whistles. |
| `cargo run --release -- live --block 128` | Ask the sound card for chunks of this many samples (1 to 16 384): smaller means less delay, but more risk of clicks. |
| `cargo run --release -- live --seconds 30` | Run for 30 s and stop on its own (good for repeatable benchmarks). |
| `cargo run --release -- devices` | List your microphones and outputs. |
| `cargo run --release -- live --output "CABLE"` | Send the voice to the first output whose name contains "CABLE" (see 1.4). |
| `cargo run --release -- bench` | Speed test with no microphone needed: 60 s of made-up voice in blocks of 256 samples (change them with `--seconds` and `--block`). |
| `cargo run --release -- file in.wav out.wav --pitch 7` | Change a recording instead of your live voice, and save it as `out.wav`. |
| `cargo run --release -- file in.wav out.wav --effect robot --freq 120` | Same, with the robot effect. |
| `cargo run --release -- file in.wav out.wav --effect 16bit` | Same, with the 16-bit console effect. |
| `cargo run --release -- file in.mp3 --effect 8bit` | Leave out the output file to **listen** to the result instead (Enter stops it early). |
| `cargo run --release -- help live` | Show every option for a command. |
| `cargo test --release` | Run the automatic checks (they confirm +12 really doubles the frequency, that the robot voice stays on its note, that the console voices keep the right number of samples and levels, and that results files never overwrite each other). |

`--effect` picks the effect: `pitch` (the default), `robot`, `4bit`, `8bit` or `16bit`. It works the same way in `live`,
`bench` and `file`. The options of each effect are ignored by the others:
`--pitch` and `--window-ms` belong to `pitch`, `--freq` belongs to `robot`, and `--bits` and
`--rate` belong to `4bit`, `8bit` and `16bit`.

`file` reads WAV, MP3, FLAC and OGG files. It always saves WAV (mono, whatever the input was), so
the output name must end in `.wav`. Without an output name it plays the result on your default
speakers or headphones and stops by itself at the end. That's the quickest way to try effects
and their settings on the same recording, again and again.

### 1.4 Using it as a microphone in other apps (Discord, Zoom...)

Apps can only pick microphones, so you need a "virtual cable": a fake speaker whose sound comes
out of a fake microphone. On Linux, PipeWire and PulseAudio can make one with two commands:

```
pactl load-module module-null-sink sink_name=voice_changer sink_properties=device.description=VoiceChanger
pactl load-module module-remap-source master=voice_changer.monitor source_name=voice_mic source_properties=device.description=VoiceMic
```

The first creates a fake speaker called "VoiceChanger", and the second turns what it plays into a
microphone called "VoiceMic". Then:

1. Start the voice changer: `cargo run --release -- live`
2. Open **pavucontrol** (`sudo apt install pavucontrol` if needed). In its **Playback** tab,
   switch the voice changer's stream to "VoiceChanger". It remembers this for next time.
3. In Discord, Zoom, OBS and so on, pick "VoiceMic" as the microphone.

These devices disappear when you log out. Run the two commands again to bring them back.
App 2 (text-to-speech into a virtual microphone) needs the same kind of virtual mic, so you
only learn this once. (On Windows the equivalent is VB-Audio Virtual Cable, and on macOS BlackHole.)

### 1.5 If something goes wrong

| Message or symptom | Fix |
|---|---|
| `can't run at 48000 Hz like the microphone` | Set your mic and output to the same sample rate in your system's sound settings. |
| Clicks or crackles, `underruns` counting up | Raise the safety queue: `--buffer-ms 20`, or use a bigger `--block`. |
| Warbly sound (`pitch` effect) | Try `--window-ms 40`. This simple method warbles a bit on pure tones; see 3.3. |
| Robot voice sounds muffled or mumbly | Raise `--freq` (try 150 to 200). A higher note puts the pulses closer together, so the words are easier to follow. |
| `8bit` voice too harsh to understand | Raise `--rate` (try 11025), or add a few bits if you lowered `--bits`. Or try `--effect 16bit`. |
| No sound | Check the mic isn't muted in pavucontrol's **Input Devices** tab, and that the voice changer's streams appear in **Recording** and **Playback**. `devices` lists everything. "PulseAudio Sound Server" goes through your desktop's sound server (PipeWire or PulseAudio), while the entries named after the sound card itself (like "HD-Audio Generic, ALC287 Analog") bypass it, and are often busy. |
| `The requested audio device is not available` (often with `ALSA lib pcm_dsnoop.c ... unable to open slave`) | The plain ALSA default can't be opened because PipeWire/PulseAudio owns the sound card. Without `--input`/`--output`, the program already prefers the `pulse` device; if you still see this, pass `--input pulse --output pulse` explicitly. |
| `output error: ALSA function 'snd_pcm_avail_delay' failed` at the end of `file` playback | Harmless. It sometimes appears as the speaker stream closes, after everything has been played. |
| `failed to run custom build command for alsa-sys` | The ALSA headers are missing: `sudo apt install libasound2-dev pkg-config`. |

---

## Part 2: The files

```
voice-changer/
├── Cargo.toml        the project's "ID card": name, version, libraries it uses
├── Cargo.lock        exact library versions, written by cargo (don't edit)
├── benchmarks/results/voice-changer/   the results files of `live` and `bench` (see 3.7)
└── src/
    │   The library: the effects and the sound plumbing, usable by other programs (like Intercom)
    ├── lib.rs        lists the library's files
    ├── effect.rs     the `--effect` choice: picks the effect and holds the options of each
    ├── pitch.rs      the pitch shifter (the sound maths)
    ├── robot.rs      the robot voice (the sound maths, including a small FFT)
    ├── retro.rs      the 4-bit, 8-bit and 16-bit console voices
    ├── devices.rs    finding microphones and speakers, opening sound streams on them
    ├── audio_file.rs reading audio files (WAV, MP3...) and changing their sample rate
    ├── testutil.rs   helpers shared by the tests (only built by `cargo test`)
    │
    │   The `voice-changer` program, built on the library
    ├── main.rs       entry point: reads the command line, calls the right part
    ├── live.rs       microphone → effect → speakers, live measurements, and playing `file` results
    ├── offline.rs    the `bench` speed test, and the `file` command
    └── results.rs    saves the numbers as JSON in benchmarks/results/voice-changer/
```

**Libraries** (Rust calls them *crates*; cargo downloads them from crates.io):

| Crate | What we use it for |
|---|---|
| `cpal` | Talks to the sound card on Windows, macOS and Linux with the same code. |
| `ringbuf` | A lock-free queue to pass audio between two threads (explained in 3.2). |
| `clap` | Turns a description of our options into a full command-line parser with `--help`. |
| `hound` | Writes WAV files. |
| `symphonia` | Reads audio files: WAV, MP3, FLAC, OGG. It unpacks ("decodes") compressed formats like MP3 back into samples. |
| `serde`, `serde_json` | Turn our results into JSON (explained in Part 4). |
| `sysinfo` | Reads your CPU model, OS and RAM for the results file. |
| `libc` | Lets us ask Linux or macOS how much CPU time and memory the program used. |
| `humantime` | Formats the date in the results file. |

Building puts the program in `target/release/voice-changer` (`.exe` on Windows). You can run
that file directly instead of `cargo run --release --`.

---

## Part 3: How the voice changer works

### 3.1 What digital audio is

A microphone measures air pressure many times per second. Each measurement is a **sample**, a
number between -1.0 and 1.0. At **48 000 Hz** (the usual rate), one second of sound is 48 000
samples. Stereo audio has 2 **channels**, stored "interleaved": left, right, left, right... We
average the channels into one (**mono**) because a voice is mono anyway.

The sound card doesn't hand over samples one at a time. It delivers them in **blocks** (say 256
samples = 5.3 ms) and asks for blocks to play. A block can only be processed once it's full, so
bigger blocks mean more delay.

### 3.2 The live path

```
microphone ─► input callback ─► ring buffer ─► output callback ─► speakers
              (the effect)       (a queue)
```

- A **callback** is a function we give to cpal, which the sound card system calls each time a
  block is ready (input) or needed (output). Those calls happen on the sound system's own
  **threads**, which are parts of the program running at the same time as the rest.
- The two callbacks run on different threads, at slightly different moments, so they need a
  queue between them: the **ring buffer**. It's a fixed-size circle of slots. One side writes,
  the other reads, and it needs no **lock**, which matters because an audio thread that waits even a few
  milliseconds produces a click.
- We start the queue with `--buffer-ms` of silence (10 ms by default) as a cushion. If the mic
  and speaker clocks drift and the queue grows, the output callback throws away the surplus to
  keep the delay low.

The `file` command doesn't need any of this, because the whole recording is there from the start.
It decodes the file with `symphonia`, mixes it to mono, and runs the effect over all of it at once.
Then it either writes a WAV with `hound`, or plays it (`play` in `live.rs`): an output callback
alone, reading straight from the finished samples. If the speakers can't run at the recording's
sample rate, the samples are converted first (`resample`: straight lines between the samples).

### 3.3 The pitch shifter (`pitch.rs`)

Play a record faster and the voice goes higher. That's the idea, but if we simply read faster
than we record, we run out of audio. The trick:

1. Keep the last ~30 ms of audio in a circular **delay line**.
2. Read from it with a "head" moving at a different speed than the writing: 1.33× speed for
   +5 semitones, 2× for +12, 0.5× for -12. (A semitone is a factor of 2^(1/12) ≈ 1.059.)
3. When a head reaches the end of the delay line, it jumps back. To hide the jump, there are
   **two heads** half a window apart, each faded in and out with a smooth curve (sin²). One
   is always silent at the moment the other jumps, and the two volumes always add up to 1.

The cost is a few multiplications per sample, and the extra delay is half the window (15 ms by
default). The downside is a slight warble, because the two heads don't always line up with the
wave. Better methods (WSOLA, phase vocoder) line them up, at the cost of more CPU and usually
more delay. That trade-off is exactly what the benchmark helps judge, so it's the natural next step.

### 3.4 The robot voice (`robot.rs`)

A voice is two things stacked. The **pitch** is how fast your vocal cords buzz, and it moves up
and down as you speak. The **vowel shape** is your throat and mouth filtering that buzz, which is
what makes "ah" sound different from "ee". A robot keeps the shape and throws away the moving
pitch: the buzz stays on one note.

To pull the two apart we use the **FFT** (Fast Fourier Transform), which splits a short slice of
sound into its frequencies. For each frequency it tells us two things: how **loud** it is (that
carries the vowel shape) and its **phase**, meaning where in its cycle that wave starts (that
decides *when* the buzz pulses happen). The trick is to keep the loudnesses and set every phase
to zero:

1. Every `hop` samples, take the last ~20 ms of sound and run the FFT on it.
2. Keep every loudness and set every phase to zero. Waves that all start at the same moment
   add up into a single short pulse, and the loudnesses give that pulse the vowel's shape.
3. Run the FFT backwards to get the pulse as a waveform, and add it to the output (the slices
   overlap, so the pulses are blended together, which is called **overlap-add**).

One pulse per `hop` samples is a buzz of `48000 / hop` Hz, no matter what pitch you spoke at.
So `hop` is the note: `--freq 100` means a pulse every 480 samples. Speak high or low, or
sing a tune, and the robot stays on its note.

The costs:

- **Delay.** The slice must be at least two pulses long to blend smoothly, so a lower note needs a
  longer slice, and the delay is the slice length: 21 ms at 100 Hz, 11 ms at 200 Hz.
- **CPU.** Two FFTs per pulse, so a bit more than the pitch shifter, but still well under 1% of
  one core. We wrote the FFT ourselves (about 40 lines, `Fft` in `robot.rs`) to avoid another crate.
- **Peaks.** Pulses are spikier than speech, so a small limiter (`soft_limit`) keeps loud
  sounds from going over 1.0, which would crackle.

### 3.5 The console voices (`retro.rs`)

Old games consoles had very little memory, so the voice clips in their games were stored with few
samples per second and few levels per sample. Those two savings *are* the sound, and copying them
is simple (this kind of effect is usually called a **bitcrusher**):

1. **Fewer samples per second.** The "chip" keeps one sample out of every few: at 8000 Hz, one
   in six of our 48 000. Nothing above half that rate (4000 Hz) can be stored, so the voice turns
   dull. High sounds like "s" don't simply disappear, though: they fold back down as metallic
   whistles. This is called **aliasing**, and normally filters are there to prevent it. Here
   it's part of the charm.
2. **Fewer levels.** Each kept sample is rounded to the nearest of a few steps: 4 bits gives 8
   steps above zero and 8 below, where a CD has 32 768 each way. The rounding error is the grit,
   and each bit fewer doubles it. Old voice clips were recorded loud, to use every step, but your
   microphone is usually much quieter. So the steps are sized to how loud you are right now (the
   **envelope**: the recent peak, which halves every 0.1 s after you get quieter), not to the
   loudest sound possible. Whisper or shout, you get the same number of steps.
   The presets keep 16 bits, which is too fine to hear, so this step only adds grit when you
   lower `--bits`.
3. **Playing it back.** `4bit` and `8bit` hold each kept sample until the next one, which cuts the wave into
   stair-steps: harsh and buzzy. `16bit` averages the samples it drops instead of skipping them
   (fewer whistles), and slides in a straight line from one kept sample to the next. That's softer
   and a little muffled, much like the SNES, which also smoothed between its samples.

| | `4bit` | `8bit` | `16bit` |
|---|---|---|---|
| `--rate` | 4000 Hz | 8000 Hz | 12 000 Hz |
| `--bits` | 16 | 16 | 16 |
| `--bits` for that era's grit | (no real console) | 4 (8 steps each side of zero) | 8 (128 steps each side) |
| between kept samples | hold (stair-steps) | hold (stair-steps) | slide (straight lines) |

The names `8bit` and `16bit` are the consoles' generations, not the bits of their sound. Plenty of
8-bit consoles played 4-bit sounds, and 16-bit ones often played 8-bit sounds. `4bit` is no real
console: it's `8bit` with half the rate, to hear how far a voice can be crushed and still be
understood. For the very bottom, try `--effect 4bit --bits 1`: each kept sample is then just
"loud up", "loud down" or nothing.

This is the cheapest effect of all (a few additions per sample), and its delay is tiny: half a
kept sample for `4bit` and `8bit` (0.13 and 0.06 ms), one and a half for `16bit` (0.13 ms).

### 3.6 What the latency numbers mean

The live mode estimates the **mouth-to-ear delay** as the sum of four parts:

| Part | What it is | Where it comes from |
|---|---|---|
| input | Time from the mic capturing a sample to our code getting it | cpal's capture timestamp |
| queue | Time spent waiting in the ring buffer | how full the queue is |
| output | Time from our code handing over a sample to it leaving the speaker | cpal's playback timestamp |
| effect | The effect's own delay: half the window for `pitch`, the slice length for `robot`, under 0.2 ms for `4bit`/`8bit`/`16bit` | computed |

The input and output timings are what your operating system reports, so they're estimates. They're
reliable on Windows (WASAPI) and macOS, and rougher on some Linux setups. Bluetooth headphones
add 100 ms or more that no program can see, so use wired headphones when benchmarking. Around
20 to 30 ms total feels natural; above ~50 ms you start to hear yourself "echo".

**Processing time** is how long the effect takes per block. **CPU load** (`rtf` in the summary) is
that time divided by the block's duration: 1% means we use 1% of the time we're allowed. The live summary
also counts **underruns** (the speaker wanted audio and the queue was empty, heard as a click)
and **overflows** (the queue was full).

### 3.7 The results file

Every `live` and `bench` run saves one JSON file in `benchmarks/results/voice-changer/` inside
this project (`--out-dir` picks another folder), named
like `20261012T172355_pitch-shift_delay-line_live.json`: the date and time (UTC), the effect's
method, and the command. A robot run is named `..._robot_zero-phase-fft_live.json`, and an 8-bit
one `..._8bit_bitcrush-hold_live.json`. Two runs in the same second would get the same name, so
the second one becomes `..._live_2.json`, then `_3` and so on: nothing is ever overwritten. The
two Python apps write the same format ("speech-bench/1") into their own results folders, so all
three can be compared directly. Here's a shortened example:

```json
{
  "schema": "speech-bench/1",
  "app": "voice-changer",
  "implementation": "rust",
  "engine": "pitch-shift:delay-line",
  "mode": "live",
  "created": "2026-10-12T17:23:55+00:00",
  "machine": { "os": "Linux (Ubuntu 24.04)", "cpu": "...", "cores": 8, "arch": "x86_64", "ram_gb": 15.7 },
  "load_ms": 4.5,
  "cpu_time_s": 0.9,
  "peak_rss_mb": 8.6,
  "summary": {
    "e2e_latency_ms": { "mean": 27.4, "p50": 27.1, "p95": 29.8, "min": 25.0, "max": 31.2 },
    "rtf": { "mean": 0.002, "...": "..." }
  },
  "samples": [ { "t_s": 1.0, "e2e_latency_ms": 27.2, "...": "..." } ],
  "settings": { "effect": "pitch", "pitch_semitones": 5.0, "window_ms": 30.0, "...": "..." },
  "counters": { "underruns": 0, "overflows": 0 }
}
```

| Field | Meaning |
|---|---|
| `load_ms` | Time to get ready: opening the audio devices (live), or creating the effect (bench). |
| `cpu_time_s`, `peak_rss_mb` | CPU time and most memory the whole program used. |
| `summary` | For each metric: average (`mean`), median (`p50`), the value 95% of measurements stay under (`p95`), lowest and highest. |
| `e2e_latency_ms` | Mouth-to-ear delay (3.6), measured 10 times a second. Also saved as `first_audio_ms`, the name the other apps use for "time until you hear sound". |
| `block_process_us` | Time spent changing each block, in microseconds (1 ms = 1000 µs). |
| `rtf` | Real-time factor: processing time divided by the audio's duration. Lower is better, and above 1.0 it can't keep up. |
| `cpu_s_per_audio_s` | CPU seconds used by the whole program per second of voice. |
| `samples` | One entry per second, to see how things change over time. |
| `settings`, `counters` | Extras for this app: the options you used, and how many clicks (underruns) happened. |

For fair comparisons, use the same machine, close other heavy programs, use wired headphones,
and use `--seconds` so every run lasts the same time.

---

## Part 4: Rust concepts used in this code

Read this next to the code; each concept points to where it's used.

**Variables and types.** `let x = 5;` creates a variable. Variables can't change unless declared
`let mut x`. Rust is strict about types: `f32` is a decimal number (32 bits), `u32`/`u64` are
non-negative whole numbers, `usize` is a whole number for positions and lengths, `bool` is
true/false, `String` is text you own, `&str` is borrowed text. Numbers of different types never
mix silently: you convert explicitly with `as`, like `sample_rate as f32` (`pitch.rs`).

**Functions.** `fn name(a: f32, b: u32) -> f32 { ... }` takes inputs and returns a value. The
last line of a function, without a `;`, is the value returned.

**Structs and `impl`.** A `struct` groups data (`PitchShifter` holds its buffer, position, phase).
An `impl` block gives it functions ("methods"). `Self` means "this type". `PitchShifter::new(...)`
creates one, and `shifter.process(...)` calls a method on it.

**Ownership: Rust's big idea.** Every value has exactly one owner, and it's freed automatically
when the owner goes away. There is no garbage collector, which is one reason Rust suits real-time
audio: nothing ever pauses the program to clean up memory. You can lend a value without giving it away:
- `&x` is a **shared borrow**: read-only, and many can exist at once.
- `&mut x` is a **mutable borrow**: allowed to change it, and only one at a time.

For example, `fn process(&mut self, samples: &mut [f32])` borrows the shifter and the samples
so it can change both, then gives them back. The compiler checks these rules before the program
runs, which is how Rust prevents two threads from changing the same data at the same time.

**Slices and `Vec`.** `Vec<f32>` is a growable list you own. `&[f32]` / `&mut [f32]` is a
**slice**, a borrowed view of part of a list. `.chunks(n)` splits it into pieces of n, which is how
we split interleaved audio into frames.

**`Option` and `Result`.** Rust has no "null" and no exceptions. Instead:
- `Option<T>` is either `Some(value)` or `None`. Example: `block: Option<u32>`, because the user may or may not pass `--block`.
- `Result<T, E>` is either `Ok(value)` or `Err(error)`. Anything that can fail returns one.
- The **`?`** operator means "if this is an error, stop and return it; otherwise give me the
  value". `input_device.default_input_config()?` is that pattern in `live.rs`.
- `Box<dyn Error>` means "any kind of error", used when several different things can fail.
- `let Some(x) = ... else { ... };` takes the value out of an `Option`, and runs the `else` part
  (which must leave the function) when there's none. `process_file` in `offline.rs` uses it:
  no output file means "play instead".

**`enum` and `match`.** An `enum` is a value that's exactly one of several variants. `Command`
in `main.rs` is `Live`, `Bench`, `File` or `Devices`. A variant can carry data: `Live(LiveOptions)`
holds the options of the `live` command. `match` runs the branch for the variant
you have, and the compiler refuses to build if you forget one. `if let Some(x) = ...` is a
short `match` for when you only care about one case. `Effect` in `effect.rs` is an enum too: it
holds a `PitchShifter`, a `Robot` or a `Retro`, and `effect.process(...)` runs whichever one it
holds. That's how `--effect` can choose at run time while the rest of the code stays the same.

**Traits.** A trait is a set of abilities a type can have, like an "interface" elsewhere. For
example, `DeviceTrait` gives a device `build_input_stream`, and `Producer`/`Consumer` give the
ring buffer `push_slice`/`pop_slice`. You have to `use` a trait to call its methods; that's why
there are lines like `use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};`.

**Generics.** `fn build_input<T>(...)` is written once and works for any sample type `T`: f32,
i16 and so on. The `where T: SizedSample, f32: FromSample<T>` lines are the requirements: "T must be
an audio sample, and convertible to f32". The compiler makes a separate fast copy for each type
actually used, so generics cost nothing at run time.

**Closures.** `|data, info| { ... }` is a small function written inline that can use variables
from around it. We hand two of them to cpal as the input and output callbacks. The `move`
keyword makes the closure *take ownership* of what it uses (the shifter, one end of the queue),
which is required because it'll keep running on another thread after `run` has moved on.

**Threads, `Arc` and atomics.** To share their latest numbers with the main thread, the audio
threads write them into an `Arc<Readings>`: an "atomically reference-counted" pointer, meaning shared
ownership across threads, freed when the last owner is done. Inside, `AtomicU64` numbers can be
written by one thread and read by another without locks: `.store(...)` writes, `.load(...)` reads,
`.fetch_add(1, ...)` adds one. `Ordering::Relaxed` says we only need each number to be correct
on its own, not in sync with the others, which is the cheapest option.

**Attributes and macros.** Lines like `#[derive(Default)]` ask the compiler to write code for
you (here: "make a version of this struct with everything at zero or empty"). The clap library
works the same way: `#[derive(Parser)]`, `#[derive(Subcommand)]` and `#[derive(Args)]` turn our
structs into the command-line parser. Each command's options are one struct, kept next to the code
that uses them (`LiveOptions` in `live.rs`, `BenchOptions` and `FileOptions` in `offline.rs`), and
the effect options they all share are `EffectArgs` in `effect.rs`. `#[test]` marks a test,
and `#[inline]` is a speed hint. Names ending in `!` are **macros**, code that writes code:
`println!` prints, `format!` builds a `String`, `vec![0.0; n]` makes a list of n zeros.

**Modules and crates.** This project is two crates: a **library** (`lib.rs`) and a **program**
(`main.rs`) that uses it. `pub mod pitch;` in `lib.rs` means "the file `pitch.rs` is part of the
library, and other crates may use it". Inside a file, only items marked `pub` can be used from
outside it. In the library, `crate::pitch::PitchShifter` is the shifter's full name; the program
(and any other project, like Intercom) calls it `voice_changer::pitch::PitchShifter`, because a
`-` in a crate's name becomes `_` in code. `mod live;` in `main.rs` adds a file to the program
only.

**Making JSON with serde (`results.rs`).** `serde` is the standard Rust library for turning
data into formats like JSON. Writing `#[derive(Serialize)]` above a struct makes serde write the
conversion code for you: each field becomes a JSON key with the same name, `Option` becomes a
value or `null`, and `Vec` becomes a list. So the `Report` struct *is* the file format, and
`serde_json::to_string_pretty(&report)` produces the text. For the free-form parts (samples,
settings) we use the `json!` macro, which lets you write JSON almost literally:
`json!({ "t_s": 1.0, "rtf": 0.002 })`. That gives a `serde_json::Value`, a type that can hold any JSON.

**`unsafe` and `#[cfg]`.** To ask Linux how much CPU time and memory we used, `results.rs` calls
the operating system's C function `getrusage`. Rust can't check C code, so the call is wrapped
in `unsafe { ... }`, which is the programmer saying "I've checked this one myself". It's rare,
and this is the only place we use it. `#[cfg(unix)]` means "compile this only on Linux/macOS",
and the `#[cfg(not(unix))]` version next to it reports `null` elsewhere.

**Comments.** `//` is a normal comment, and `///` documents the item below it (clap even turns
them into `--help` text). `//!` documents the whole file.

### Where to go next

- Try changing the default pitch in `effect.rs` (`default_value_t = 5.0`), rebuild, and run.
- Add an effect of your own: add a variant to `EffectKind` and `Effect` in `effect.rs`, and
  the compiler will point at every `match` that needs a new line.
- *The Rust Book* (free, <https://doc.rust-lang.org/book/>), chapters 3 to 6, covers almost everything above.
- `cargo clippy` is a built-in reviewer that suggests better ways to write things.

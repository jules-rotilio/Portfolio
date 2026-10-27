"""Draws the README's diagrams (readme/images/*.svg).

    python3 readme/tools/diagrams.py

Each diagram is a function below: boxes and arrows at fixed positions, in
pixels. Change one, run this again, and look at the SVG in a browser.
Standard library only.
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "images"

# Kinds of boxes: (fill, border).
KINDS = {
    "input": ("#e8f1fd", "#3b7dd8"),
    "process": ("#fff4e0", "#d98e0b"),
    "queue": ("#f1edfd", "#7c5cd6"),
    "output": ("#e6f6ef", "#2e9d6a"),
    "outside": ("#f0f1f3", "#8a8f98"),
    "group": ("#fbfbfc", "#c3c7cf"),
    "note": ("#ffffff", "#c3c7cf"),
}
# Colors of the streams of sound, for arrows and the legend.
VOICE, PROGRAM, CLIPS, CONTROL = "#d98e0b", "#3b7dd8", "#2e9d6a", "#5b6270"
TEXT, MUTED = "#1d2330", "#5b6270"


class Svg:
    def __init__(self, width: int, height: int, title: str):
        self.width, self.height = width, height
        self.parts = [
            f'<rect x="0" y="0" width="{width}" height="{height}" rx="14" fill="#ffffff"/>',
            self._text(24, 40, title, size=22, weight="700"),
        ]
        self.markers: set[str] = set()

    @staticmethod
    def _text(x, y, text, size=14, weight="400", color=TEXT, anchor="start", italic=False):
        style = ' font-style="italic"' if italic else ""
        return (
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}"{style}>{escape(text)}</text>'
        )

    def text(self, x, y, text, **kw):
        self.parts.append(self._text(x, y, text, **kw))

    def box(self, x, y, w, h, title, lines=(), kind="process", dashed=False, small_title=False):
        """A rounded box: a bold title, then lines (a line starting with "~" is grey)."""
        fill, stroke = KINDS[kind]
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.6"{dash}/>'
        )
        if small_title:
            self.text(x + 12, y + 20, title.upper(), size=12, weight="700", color=MUTED)
            ty = y + 42
        else:
            self.text(x + 12, y + 24, title, size=15, weight="700")
            ty = y + 46
        for line in lines:
            grey = line.startswith("~")
            self.text(x + 12, ty, line.lstrip("~"), size=13, color=MUTED if grey else TEXT)
            ty += 19

    def arrow(self, points, color=CONTROL, label=None, label_at=None, dashed=False, width=2.2):
        """A line through `points`, with a head at the end; `label` near `label_at`."""
        marker = f"head{color.strip('#')}"
        if marker not in self.markers:
            self.markers.add(marker)
            self.parts.insert(
                0,
                f'<defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" '
                f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker></defs>',
            )
        path = " ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        self.parts.append(
            f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="round"{dash} marker-end="url(#{marker})"/>'
        )
        if label:
            lx, ly = label_at or points[0]
            self.text(lx, ly, label, size=12, color=color, weight="600")

    def line(self, points, color, width=2.2, dashed=False):
        path = " ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        self.parts.append(
            f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="round"{dash}/>'
        )

    def legend(self, x, y, items):
        for i, (color, label) in enumerate(items):
            ly = y + i * 20
            self.line([(x, ly), (x + 26, ly)], color, width=3)
            self.text(x + 34, ly + 4, label, size=12, color=MUTED)

    def save(self, name: str):
        body = "\n".join(self.parts)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" '
            f'font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif">\n{body}\n</svg>\n'
        )
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_text(svg)
        print(OUT / name)


def audio_engine():
    s = Svg(1260, 900, "The audio engine (audio.rs)")
    s.legend(1010, 26, [(VOICE, "your voice"), (PROGRAM, "captured program"), (CLIPS, "sounds, chimes")])

    # Inputs.
    s.text(24, 80, "INPUTS", size=12, weight="700", color=MUTED)
    s.box(20, 95, 220, 100, "Physical mic", ["cpal input stream", "~its sample rate is the", "~engine's rate"], kind="input")
    s.box(20, 360, 220, 110, "Captured program", ["programs.rs", "~Linux: PipeWire links", "~Windows: process loopback"], kind="input")
    s.box(20, 510, 220, 90, "Sound files", ["decoded once, resampled", "~to each device's rate"], kind="input")
    s.box(20, 640, 220, 90, "Chimes, announcements", ["auto-click beeps,", "~“voice changer on / off”"], kind="input")

    # The mic's chain, in the mic's audio callback.
    s.box(265, 60, 705, 160, "Mic input callback (audio thread)", kind="group", small_title=True)
    s.box(280, 100, 140, 100, "Offset removed", ["DcBlock, 20 Hz", "~gate.rs"])
    s.box(440, 100, 100, 100, "Mic meter", ["peak", "~“Mic in”"])
    s.box(560, 100, 175, 100, "Noise gate", ["floor = quietest", "~moment of 4 s;", "~opens at floor + margin"])
    s.box(755, 100, 200, 100, "Voice effect", ["pitch · robot · 4/8/16-bit", "~only while Voice ON", "~or Test is on"])
    s.arrow([(240, 145), (280, 145)], VOICE)
    s.arrow([(420, 150), (440, 150)], VOICE)
    s.arrow([(540, 150), (560, 150)], VOICE)
    s.arrow([(735, 150), (755, 150)], VOICE)

    # Queues between the threads.
    s.text(762, 628, "LOCK-FREE QUEUES", size=12, weight="700", color=MUTED)
    s.box(760, 265, 190, 85, "Voice queues", ["one per output that", "~wants the voice"], kind="queue")
    s.box(760, 380, 190, 85, "Program queues", ["ProgramTap: one per", "~output others hear"], kind="queue")
    s.box(760, 520, 190, 85, "Command queues", ["Play · Stop · Cue", "~one per output"], kind="queue")
    s.arrow([(855, 200), (855, 265)], VOICE, label="a copy to each", label_at=(862, 238))
    s.arrow([(240, 415), (760, 415)], PROGRAM, label="ProgramTap.push", label_at=(560, 405))

    # The player, between the keys and the outputs.
    s.box(280, 505, 250, 120, "Player", ["picks one of a key's files,", "~the clip cache keeps it", "~decoded at each rate", "Play(key), Stop, Cue"])
    s.arrow([(240, 555), (280, 555)], CLIPS)
    s.arrow([(240, 685), (405, 685), (405, 625)], CLIPS)
    s.arrow([(530, 562), (760, 562)], CLIPS, label="one command per output", label_at=(560, 552))
    s.text(282, 495, "from the hotkeys thread or a click", size=12, color=MUTED, italic=True)

    # Outputs: one stream per device, roles mixed.
    s.text(992, 252, "OUTPUTS · one stream per device", size=12, weight="700", color=MUTED)
    s.box(990, 265, 250, 200, "Virtual output", [
        "~others hear it",
        "your voice (while ON)",
        "+ sounds × sound volume",
        "+ program × program volume",
        "~→ “Virtual mic” meter",
        "~Linux: Intercom Output → Mic",
        "~Windows: CABLE Input → Output",
    ], kind="output")
    s.box(990, 485, 250, 175, "Headset", [
        "~you hear it",
        "sounds × sound × headset vol.",
        "+ chimes × headset volume",
        "+ your voice while Test is on",
        "~a captured program plays",
        "~here by itself, not twice",
    ], kind="output")
    s.box(990, 680, 250, 65, "Voice test device", ["~optional: your voice in Test"], kind="output")

    # Queues to outputs.
    s.arrow([(950, 300), (990, 300)], VOICE)
    s.line([(950, 325), (968, 325), (968, 712)], VOICE)
    s.arrow([(968, 590), (990, 590)], VOICE)
    s.arrow([(968, 712), (990, 712)], VOICE)
    s.arrow([(950, 415), (990, 415)], PROGRAM)
    s.line([(950, 562), (978, 562)], CLIPS)
    s.line([(978, 360), (978, 562)], CLIPS)
    s.arrow([(978, 360), (990, 360)], CLIPS)
    s.arrow([(978, 545), (990, 545)], CLIPS)

    # Control.
    s.box(20, 775, 1220, 105, "Control, without waiting", [
        "The window and the hotkeys thread change plain atomic numbers: voice ON, Test, the volumes, the gate's switch and margin. They read back",
        "the meters' peaks, the noise floor and the underruns. A new effect travels to the mic thread through a queue, and the old one comes back",
        "through another to be freed there: the audio threads never wait for a lock and never allocate, so the sound has no cracks.",
    ], kind="note")
    s.save("audio-engine.svg")


def overview():
    s = Svg(1260, 720, "How Intercom is put together: one thread per job")
    s.legend(1040, 26, [(CONTROL, "messages, shared state"), (VOICE, "sound")])

    s.text(24, 80, "YOUR COMPUTER", size=12, weight="700", color=MUTED)
    s.box(20, 95, 210, 75, "Keyboard", ["~and mouse buttons", "~that send keys"], kind="outside")
    s.box(20, 330, 210, 60, "Your mic", kind="outside")
    s.box(20, 420, 210, 75, "Programs playing", ["~Spotify, a browser…"], kind="outside")

    s.box(300, 70, 310, 130, "Window thread", ["app.rs, settings.rs (egui)", "~draws both windows, edits the", "~config; Save / Undo (undo.rs)", "~config.toml, state.toml"])
    s.box(300, 240, 310, 75, "Hotkeys", ["~/dev/input, or a keyboard hook", "~(hotkeys/): only listens"])
    s.box(300, 350, 310, 110, "Controller", ["controller.rs: key → action", "~play, stop, pages, volume,", "~voice ON/OFF, announcements", "~+ focus: the program in front"])
    s.box(300, 500, 310, 80, "Mouse", ["~auto-click and drift (mouse/),", "~one thread, sleeps until due"])

    s.box(680, 70, 270, 80, "Media", ["~media.rs: “Now playing”,", "~asks every second"])
    s.box(680, 180, 270, 100, "Programs", ["~programs.rs: lists who plays", "~sound, keeps the capture of", "~the chosen one going"])
    s.box(680, 320, 270, 170, "Audio engine", ["audio.rs (+ gate.rs)", "~the mic stream: offset, gate,", "~effect; one output stream", "~per device; the Player for", "~sound clips", "~(next diagram)"], kind="queue")
    s.box(680, 530, 270, 90, "Virtual mic", ["~virtual_mic.rs: creates it (Linux)", "~or finds VB-Cable (Windows);", "~default_mic.rs"])

    s.text(1012, 80, "OTHER PROGRAMS, DEVICES", size=12, weight="700", color=MUTED)
    s.box(1010, 95, 230, 75, "Media players", ["~MPRIS (Linux),", "~media sessions (Windows)"], kind="outside")
    s.box(1010, 320, 230, 90, "Discord, the game", ["~listen to the virtual mic:", "~your voice, sounds, program"], kind="outside")
    s.box(1010, 440, 230, 70, "Your headset", ["~sounds, chimes, voice test"], kind="outside")
    s.box(1010, 540, 230, 75, "The game window", ["~gets the clicks and the", "~mouse moves"], kind="outside")

    # Keys.
    s.arrow([(230, 132), (265, 132), (265, 277), (300, 277)])
    s.arrow([(455, 315), (455, 350)], label="key events", label_at=(462, 347))
    s.arrow([(610, 405), (680, 405)], label="Player", label_at=(622, 397))
    s.arrow([(455, 460), (455, 500)], label="every key", label_at=(462, 485))
    s.arrow([(610, 560), (650, 560), (650, 650), (985, 650), (985, 590), (1010, 590)])
    # Window.
    s.arrow([(610, 110), (680, 110)])
    s.arrow([(560, 200), (560, 240), (560, 350)], dashed=True)
    s.text(568, 230, "bindings", size=12, color=CONTROL, weight="600")
    s.arrow([(610, 170), (645, 170), (645, 360), (680, 360)], dashed=True)
    s.text(616, 190, "settings", size=12, color=CONTROL, weight="600")
    s.arrow([(610, 140), (630, 140), (630, 230), (680, 230)], dashed=True)
    # Outside sources.
    s.arrow([(230, 360), (260, 360), (260, 470), (640, 470), (680, 470)], VOICE)
    s.arrow([(230, 457), (250, 457), (250, 330), (662, 330), (662, 250), (680, 250)], VOICE)
    s.arrow([(815, 280), (815, 320)], VOICE, label="ProgramTap", label_at=(822, 305))
    s.arrow([(1010, 132), (950, 132)], label="tracks", label_at=(958, 124))
    # Sound out.
    s.arrow([(950, 365), (1010, 365)], VOICE)
    s.arrow([(950, 470), (1010, 470)], VOICE)
    s.arrow([(815, 490), (815, 530)], dashed=True)
    s.save("overview.svg")


def program_capture():
    s = Svg(1260, 600, "Capture program audio: others hear a copy, you hear the program once")
    s.legend(1060, 26, [(PROGRAM, "the program's sound"), (CONTROL, "Intercom's helpers")])

    # Linux.
    s.box(20, 60, 600, 470, "Linux · PipeWire", kind="group", small_title=True)
    s.box(40, 100, 170, 70, "Spotify", ["~its sound stream"], kind="input")
    s.box(430, 100, 170, 70, "Your headset", ["~as always"], kind="outside")
    s.arrow([(210, 125), (430, 125)], PROGRAM, label="its usual link", label_at=(270, 116))
    s.box(250, 210, 200, 85, "Intercom Apps", ["~a speaker that plays", "~nowhere (null sink)"], kind="process")
    s.arrow([(130, 170), (130, 252), (250, 252)], PROGRAM, label="+ links by pw-link", label_at=(138, 205))
    s.box(250, 330, 200, 70, "Intercom records", ["~its monitor (cpal)"], kind="process")
    s.arrow([(350, 295), (350, 330)], PROGRAM)
    s.box(250, 435, 200, 75, "Engine → Intercom Mic", ["~at “Volume for others”"], kind="output")
    s.arrow([(350, 400), (350, 435)], PROGRAM, label="ProgramTap", label_at=(358, 422))
    s.box(470, 210, 135, 190, "Helpers", ["~pw-dump finds", "~the ports;", "~pactl subscribe", "~says when a new", "~stream starts (a", "~new video): links", "~checked again"], kind="note")
    s.text(40, 470, "Picking “None” removes", size=12, color=MUTED)
    s.text(40, 488, "Intercom Apps, links and all.", size=12, color=MUTED)

    # Windows.
    s.box(640, 60, 600, 470, "Windows 10 (2004) or later", kind="group", small_title=True)
    s.box(660, 100, 190, 85, "Spotify.exe", ["~and its child processes,", "~which play the sound"], kind="input")
    s.box(1050, 100, 170, 70, "Your headset", ["~as always"], kind="outside")
    s.arrow([(850, 125), (1050, 125)], PROGRAM, label="plays as usual", label_at=(900, 116))
    s.box(870, 210, 230, 100, "Process loopback", ["~the system records one", "~program's sound and its", "~children, untouched"], kind="process")
    s.arrow([(755, 185), (755, 260), (870, 260)], PROGRAM)
    s.box(870, 340, 230, 70, "Capture thread", ["~float or 16-bit, to mono"], kind="process")
    s.arrow([(985, 310), (985, 340)], PROGRAM)
    s.box(870, 435, 230, 75, "Engine → CABLE Input", ["~→ CABLE Output (Discord)"], kind="output")
    s.arrow([(985, 410), (985, 435)], PROGRAM, label="ProgramTap", label_at=(993, 427))
    for i, line in enumerate([
        "The audio sessions (like the",
        "volume mixer) list who plays.",
        "Intercom records the topmost",
        "process with the same .exe,",
        "which includes the children.",
    ]):
        s.text(660, 330 + i * 18, line, size=12, color=MUTED)

    s.text(24, 565, "Turning the voice changer ON sets the capture back to “None”. Intercom itself and Discord are never offered: your friends would hear themselves.", size=13, color=TEXT)
    s.save("program-capture.svg")


if __name__ == "__main__":
    audio_engine()
    overview()
    program_capture()

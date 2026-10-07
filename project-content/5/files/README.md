# MediaToolkit

MediaToolkit is a desktop media explorer for browsing, previewing, tagging, finding duplicates, and processing a media library.

## Features

- Browse folders and files with a folder tree, a detailed list or a **thumbnail grid** (List/Grid buttons; thumbnails are made in the background for images and video first frames), Back/Forward/Up navigation (Alt+Left/Right/Up), a name filter (**Ctrl+F**, Esc clears it), a tag search, and media-type filters. Hidden files are excluded.
- Search by tags with **Tags** in the Explorer toolbar. Tick **Has** or **Not** next to each tag (type in *Find a tag* to narrow the list) and choose whether files need *all* checked tags (AND) or *any* of them (OR); files with a **Not** tag are always excluded. Tick **Search the whole catalog** to list matching files from every indexed folder; right-click a result and choose **Show in folder**, or click **Back to folder**. Hover over a file to see its tags.
- Choose a light or dark theme, or follow the desktop setting, under **View → Theme**. The choice is remembered.
- The Explorer toolbar keeps file actions (New folder, Rename, Cut, Copy, Paste, Move to Trash) together, puts **Edit tags** and **Index folder** next to them, and groups rarer commands under **More** (Load tags.json…, Copy random media…, Rename files with GUIDs…). Buttons grey out when they do not apply to the selection.
- On launch, open the saved default directory (initial fallback: `Path.home()`). Use **Set as start folder** in Explorer to save the currently open directory for future launches.
- Create a timestamped log file for each launch in `~/.local/share/MediaToolkit/logs/`; the 20 most recent are kept. Logs include application status messages, indexing progress (every 10%) and each file that is hashed, background processing activity, reported errors, and warnings from Qt and libraries. Each line names the thread that wrote it. Set `MEDIA_TOOLKIT_LOG_LEVEL=DEBUG` for more detail, such as cache reuse for unchanged files.
- Create folders; rename, copy, move, and send items to the system Trash.
- In Explorer, copy a random selection of media from the current folder and its subfolders into a new named folder in the system temporary folder (usually `/tmp`), choosing the extensions and requested count. Hidden files are skipped. Rename files directly in the current folder to GUID-based filenames while preserving extensions; nested folders are left unchanged.
- Show Explorer controls only on the Explorer tab, with separate Trash actions for selected entries in Disk Usage and duplicate files in Duplicates.
- Preview still images, animated GIFs, animated WebP, video, and audio. Media details include format, duration, codecs, resolution, frame rate, audio channels, sample rate, and bit rate when available.
- Video previews show an extracted first-frame thumbnail before playback.
- View folder sizes, file counts, and subfolder counts.
- Index supported media into a shared SQLite catalog/cache. The index stores file size and modification time, SHA-256, perceptual hashes for still images and a configurable number of sampled frames from videos and animated GIFs, and ffprobe metadata. Unchanged files can reuse their cached information. Several files are indexed in parallel and results are saved as they complete; closing the app stops indexing promptly and keeps everything indexed so far. Closing while media processing runs asks for confirmation, then stops FFmpeg and removes unfinished output.
- Find exact duplicates for indexed media, visually similar still images, and similar videos/animated GIFs whose sampled frames match. Still images also match a video or animated GIF if any sampled frame is visually similar.
- Adjust preferences under **Settings → Preferences…** (Ctrl+,): theme, thumbnail size, files indexed at once, duplicate image similarity (differing fingerprint bits allowed) and matching video frames, and how many log files to keep. The number of frames sampled from videos and animated GIFs is `VIDEO_HASH_FRAME_COUNT` in `media_toolkit/media/indexer.py`.
- Review duplicate groups with an in-tab preview and per-file/group-total sizes. Duplicate matching runs only when you click **Refresh duplicate groups**; click it after indexing or changing files to update the list and remove records for files deleted outside the app. Records under a scan folder that is currently unavailable (for example an unmounted drive) are kept with their tags. Mark false-positive groups as not duplicates; these choices persist in the database and can be restored later.
- Browse the app database in a read-only Database tab, with table selection, text filtering, and paginated rows.
- Assign tags from the bundled [`tags.json`](./tags.json) taxonomy. The app stores tags in its database and imports/synchronizes Linux desktop `user.xdg.tags` extended attributes where supported. Use **Load tags.json…** to load another taxonomy.
- Use the Process tab to save and run ordered FFmpeg workflows with Trim, Resize, Convert format, and Extract audio blocks. Output files are written separately and existing files are not overwritten.
- The separate Quick Process tab follows the file selected in Explorer, provides a preview, and presents media-specific options for extracting the first frame from video/GIF/WebP, animated image conversion, audio conversion, trimming, resizing, audio extraction/muxing, and appending audio or video. Conversion and resize controls use the source frame rate and dimensions as defaults, with aspect-ratio-preserving width and height limits. Animated WebP output has an adjustable quality slider from 0 (worst) to 100 (best). GIF/WebP conversions can split the selected time range into up to 100 equal-length output files, with the per-part duration shown in the controls. Start/end checkboxes allow processing from the beginning, through the end, or across the whole file. Pillow handles animated WebP-to-GIF conversion and first-frame extraction for compatibility with FFmpeg builds that cannot decode animated WebP.

Explorer row colors show media state (a legend sits below the file list):

| Color | Meaning |
| --- | --- |
| Grey | Not yet indexed |
| Amber | Indexed, no tags |
| Green | Indexed and tagged |
| Red | Duplicate detected (takes precedence over tag state) |

Both themes use soft tints with matching text colors that meet WCAG AA contrast.

The catalog and workflow definitions are stored in `media-toolkit.sqlite3` under the platform's Qt `AppDataLocation` (on Linux, typically `~/.local/share/MediaToolkit/`). On first launch after the app-data directory name changes, an existing database in `~/.local/share/main.py/` is copied to the new location. The database can be reused across browsing sessions; it is not a database shared between separate computers or users.

## Requirements

- Python 3.10 or newer
- FFmpeg and `ffprobe` on `PATH` for media processing and technical media details
- Qt Multimedia backend support for the codecs used by the previewed media

Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Or install them in a virtual environment to keep them separate from your system Python:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

```bash
python main.py
```

`python -m media_toolkit` starts the app as well.

If you installed the dependencies in a virtual environment, activate it first with `source .venv/bin/activate`.

## Project structure

```
main.py                    Entry point (also: python -m media_toolkit)
tags.json                  Default tag taxonomy loaded into a new catalog
media_toolkit/
  app.py                   Startup: logging, app-data catalog, main window
  logging_setup.py         Per-launch log files and Qt message capture
  app_settings.py          User preferences with defaults and limits
  core/                    Catalog and file handling, independent of Qt
    database.py            SQLite catalog: media records, tags, duplicates, workflows
    filesystem.py          Media extensions, folder listing, disk-usage scan
    file_operations.py     Rename, copy/move, trash, random copy, GUID rename
    xdg_tags.py            Linux user.xdg.tags extended attributes
    tag_query.py           Tag search conditions (all of / any of / none of)
  media/                   Reading media with FFmpeg and Pillow
    ffmpeg_tools.py        Finding FFmpeg, running ffprobe and cancellable commands
    media_info.py          Technical details shown in previews
    indexer.py             Hashing and probing one file for the catalog
  processing/              Conversions, independent of Qt widgets
    workflow.py            Saved multi-step workflows (Process tab)
    quick.py               Quick Process operations and FFmpeg/Pillow commands
  ui/                      Qt widgets and background workers
    main_window.py         Hosts the tabs and coordinates shared actions
    explorer_tab.py, disk_usage_tab.py, duplicates_tab.py,
    workflow_tab.py, quick_process_tab.py, database_browser.py
    preview.py, tag_editor.py, filter_model.py
    tag_filter.py          Tags button and panel for AND / OR / NOT tag searches
    catalog_results.py     Results list for whole-catalog tag searches
    thumbnails.py          Background thumbnail cache and grid delegate
    settings_dialog.py     Preferences dialog
    theme.py               Light/dark palettes, stylesheet, status colors
    icons/                 App icon (app-icon.png) and small SVGs used by the stylesheet
    index_worker.py        Background indexing thread
    background.py          Runs blocking calls off the UI thread
tests/                     unittest suite
```

Run the tests with:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
```

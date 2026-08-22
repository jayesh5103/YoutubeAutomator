# Antigravity Implementation Prompt: Video Review, Editing & Mandatory Approval Workflow

## How to use this document
This is a complete, self-contained implementation brief. Treat it as the full spec for this session — no other context should be assumed beyond what's written here and what you find by inspecting the actual codebase. Where this document's assumptions about existing file/table structure turn out to be wrong, adapt to match what actually exists rather than blocking on it, and leave a short comment explaining the deviation.

---

## 1. Project Context (recap)

**YoutubeAutomator** is a Python system that automatically produces and uploads DSA/coding-education YouTube Shorts in Hinglish. The current pipeline, fully automated end-to-end, is:

1. `youtube_intelligence.py` — scrapes trending topics + competitor channels, sends metadata to Groq (`llama-3.3-70b-versatile`) to produce structured Hinglish video ideas with demand scores.
2. Script + storyboard generation — an LLM call breaks a ~50-60s script into 5-9 **storyboard beats**, each with spoken text, a visual action (`show_array`, `highlight_element`, `show_pointers`, `show_code`, etc.), and a JSON params dict.
3. `beat_renderer.py` — for each beat, generates the TTS voiceover first, measures its exact duration, then compiles a Manim scene scaled to that duration, so visuals stay millisecond-synced to narration.
4. `video_editor.py` (MoviePy) — stitches beat clips together, mixes background music at 15% volume, burns in SRT-style subtitles, resizes to 720x1280.
5. `is_clip_healthy()` — validates the final file (size, header integrity, black/green-frame sampling, frozen-frame diff check) before it's allowed to proceed.
6. `youtube_uploader.py` — OAuth2 + resumable chunked upload directly to the channel, currently triggered automatically once the health check passes.
7. `database.py` (SQLite) — stores analytics, niche performance scores, and a global API-cooldown lock used to avoid Groq/Manim 429s across threads.
8. `gui.py` (CustomTkinter) — a desktop control center. It auto-relaunches itself inside its venv if not already running there, runs all heavy work (rendering, uploads, scraping) on background `threading.Thread`s so the Tkinter mainloop never freezes, and redirects `stdout` into a live console textbox via a custom `ConsoleDirector` queue.

**Today's gap:** step 6 fires automatically the moment step 5 passes. There is no point where a human sees the script or the finished video before it goes live, and there's no structured record of what happened during a given video's generation.

---

## 2. What this feature adds

Three things, all inside the existing `gui.py` desktop app (no new web app):

1. **A mandatory approval gate.** No video may reach `youtube_uploader.py` without an explicit human "Approve & Upload" action in the GUI. This is a hard rule, not a default — every single video stops and waits, regardless of how clean its health check was.
2. **Two review/edit checkpoints:**
   - **Script review**, before rendering starts — edit any beat's spoken line (and, if needed, its visual action/params), then approve to kick off rendering.
   - **Video review**, after rendering finishes — a full editing surface: reorder/cut clips on a timeline, trim the final video's start/end, swap background music, hand-correct captions, and regenerate individual beats without re-rendering the whole video. Then approve, reject-with-notes, or save-and-come-back-later.
3. **Structured logging** of every pipeline stage (trend scrape, script gen, per-beat render, TTS, assembly, health check, upload), viewable and filterable inside the GUI, in addition to whatever file/console logging already exists.

---

## 3. Pipeline state machine

Replace the current implicit "render then upload" flow with an explicit state machine. Add a `pipeline_state.py` module owning this:

```python
from enum import Enum

class PipelineStatus(str, Enum):
    DRAFT = "DRAFT"                        # topic chosen, nothing generated yet
    SCRIPT_GENERATED = "SCRIPT_GENERATED"   # LLM produced script + beats
    SCRIPT_REVIEW = "SCRIPT_REVIEW"         # waiting on human in Script Editor panel
    RENDERING = "RENDERING"                 # beat_renderer + TTS + assembly running
    RENDERED = "RENDERED"                   # final mp4 exists, health check passed
    PENDING_REVIEW = "PENDING_REVIEW"       # waiting on human in Review & Approve tab
    NEEDS_REGENERATION = "NEEDS_REGENERATION"  # specific beat(s) flagged, looping back
    APPROVED = "APPROVED"                   # human approved, upload may proceed
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    REJECTED = "REJECTED"                   # human rejected, needs rework or discard
    FAILED = "FAILED"                       # unrecoverable pipeline error

# Legal transitions — enforce this, don't let code skip states
TRANSITIONS = {
    PipelineStatus.DRAFT: {PipelineStatus.SCRIPT_GENERATED, PipelineStatus.FAILED},
    PipelineStatus.SCRIPT_GENERATED: {PipelineStatus.SCRIPT_REVIEW, PipelineStatus.FAILED},
    PipelineStatus.SCRIPT_REVIEW: {PipelineStatus.RENDERING, PipelineStatus.REJECTED},
    PipelineStatus.RENDERING: {PipelineStatus.RENDERED, PipelineStatus.FAILED, PipelineStatus.NEEDS_REGENERATION},
    PipelineStatus.RENDERED: {PipelineStatus.PENDING_REVIEW, PipelineStatus.FAILED},
    PipelineStatus.PENDING_REVIEW: {
        PipelineStatus.APPROVED, PipelineStatus.REJECTED,
        PipelineStatus.NEEDS_REGENERATION, PipelineStatus.PENDING_REVIEW,  # save-as-draft, stays put
    },
    PipelineStatus.NEEDS_REGENERATION: {PipelineStatus.RENDERING},
    PipelineStatus.APPROVED: {PipelineStatus.UPLOADING},
    PipelineStatus.UPLOADING: {PipelineStatus.UPLOADED, PipelineStatus.FAILED},
    PipelineStatus.REJECTED: {PipelineStatus.SCRIPT_REVIEW, PipelineStatus.DRAFT},  # human chooses where to restart
}

def transition(pipeline_id: int, new_status: "PipelineStatus", note: str | None = None):
    """Validate + apply a status change, writing to video_pipeline and pipeline_log.
    Raise ValueError on an illegal transition — never silently allow one."""
```

**Hard rule to enforce in code, not just convention:** `youtube_uploader.upload_video(pipeline_id)` must begin with an assertion that the row's status is exactly `APPROVED`, and raise `PermissionError` otherwise. This is the actual mechanism that makes "every video needs manual approval" true — it must not be bypassable from the batch runner or any scheduled job.

---

## 4. Database schema (`database.py`, SQLite)

Add these tables. Match existing naming/style conventions found in the current `database.py` rather than inventing new ones if they conflict.

```sql
CREATE TABLE IF NOT EXISTS video_pipeline (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT NOT NULL,
    niche           TEXT,
    status          TEXT NOT NULL DEFAULT 'DRAFT',
    script_json     TEXT,           -- current full beats array as JSON
    script_version  INTEGER DEFAULT 1,
    video_path      TEXT,           -- latest assembled mp4
    thumbnail_path  TEXT,
    title           TEXT,
    description     TEXT,
    tags            TEXT,           -- comma-separated
    rejection_reason TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at     TIMESTAMP,
    uploaded_at     TIMESTAMP,
    youtube_video_id TEXT
);

CREATE TABLE IF NOT EXISTS script_edit_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id  INTEGER NOT NULL REFERENCES video_pipeline(id),
    version      INTEGER NOT NULL,
    script_json  TEXT NOT NULL,
    edited_by    TEXT DEFAULT 'user',   -- 'user' or 'system'
    edit_note    TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS beat_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id     INTEGER NOT NULL REFERENCES video_pipeline(id),
    beat_index      INTEGER NOT NULL,
    beat_json       TEXT NOT NULL,   -- {text, visual_action, params}
    clip_path       TEXT,
    audio_path      TEXT,
    duration_seconds REAL,
    is_current      INTEGER DEFAULT 1,   -- 1 = the version used in the current assembly
    render_status   TEXT DEFAULT 'PENDING',  -- PENDING, RENDERING, DONE, FAILED
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS timeline_edits (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id   INTEGER NOT NULL REFERENCES video_pipeline(id),
    edit_type     TEXT NOT NULL,  -- TRIM_START, TRIM_END, REORDER, CUT_BEAT, MUSIC_SWAP, CAPTION_EDIT
    edit_payload  TEXT NOT NULL,  -- JSON details of the edit
    applied_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id  INTEGER REFERENCES video_pipeline(id),
    stage        TEXT NOT NULL,  -- TREND_SCRAPE, SCRIPT_GEN, BEAT_RENDER, TTS, ASSEMBLY, HEALTH_CHECK, UPLOAD, EDIT
    level        TEXT DEFAULT 'INFO',  -- INFO, WARNING, ERROR
    message      TEXT NOT NULL,
    duration_ms  INTEGER,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Add corresponding functions to `database.py`:
`create_pipeline_entry`, `get_pipeline(pipeline_id)`, `update_pipeline_status`, `save_script_version`, `save_beat_version`, `mark_beat_current`, `record_timeline_edit`, `log_pipeline_event(pipeline_id, stage, level, message, duration_ms=None)`, `get_videos_by_status(status)`, `get_pipeline_logs(pipeline_id, stage=None, level=None, date_from=None, date_to=None)`.

---

## 5. Backend modules

### 5.1 `pipeline_state.py` (new)
The `PipelineStatus` enum and `transition()` function from Section 3. Every stage of the existing pipeline (`youtube_intelligence.py`, script gen, `beat_renderer.py`, `video_editor.py`, `youtube_uploader.py`) should call `transition()` at its natural entry/exit points instead of just proceeding to the next function call.

### 5.2 Structured logging (extend or add `logger_utils.py`)
Wrap Python's `logging` module so every stage writes to *both* the existing file/console logging and the new `pipeline_log` table. Provide a context manager:

```python
@contextmanager
def stage_timer(pipeline_id: int, stage: str):
    start = time.monotonic()
    try:
        yield
        log_pipeline_event(pipeline_id, stage, "INFO", f"{stage} completed",
                            duration_ms=int((time.monotonic() - start) * 1000))
    except Exception as e:
        log_pipeline_event(pipeline_id, stage, "ERROR", str(e),
                            duration_ms=int((time.monotonic() - start) * 1000))
        raise
```
Wrap each existing pipeline stage's body in `with stage_timer(pipeline_id, "BEAT_RENDER"): ...` etc.

### 5.3 `script_review_manager.py` (new)
- `get_script_for_review(pipeline_id)` → returns the beats array plus edit history.
- `save_script_edit(pipeline_id, updated_beats, edit_note=None)` → bumps `script_version`, inserts into `script_edit_history`, updates `video_pipeline.script_json`. Does **not** change status by itself.
- `approve_script(pipeline_id)` → `transition(SCRIPT_REVIEW → RENDERING)`, then kicks off `beat_renderer.py` for the current (possibly edited) beats.

### 5.4 `beat_renderer.py` (modify)
Add `render_single_beat(pipeline_id, beat_index, beat_json)`:
- Inserts a new `beat_versions` row, `render_status = RENDERING`.
- Runs TTS → duration measurement → scaled Manim scene, exactly like the existing full-render path but for one beat.
- On success: sets `render_status = DONE`, `is_current = 1` for this row, `is_current = 0` for the previous version of the same `beat_index`.
- This lets a single beat be redone (because a diagram is wrong, timing is off, etc.) without re-rendering the other 4-8 beats.

### 5.5 `video_editor.py` (modify)
Add, on top of the existing MoviePy assembly logic:
- `reassemble_from_timeline(pipeline_id, timeline_spec)` — `timeline_spec` is an ordered list of `{beat_id, trim_start, trim_end, include: bool}`. Re-stitches the *existing* rendered clips in the new order/trim/inclusion — this must not re-invoke Manim, only re-run the MoviePy concatenation + music + subtitle burn step, so it's fast.
- `swap_background_music(pipeline_id, new_track_path)` — re-mixes audio only (same 15% volume convention as today), doesn't touch visuals.
- `trim_final_video(pipeline_id, start_seconds, end_seconds)` — trims the assembled output.
- `regenerate_captions(pipeline_id, edited_lines)` — takes hand-corrected caption text per beat, regenerates the SRT and re-burns subtitles without touching the underlying video track.

Each of these writes a row to `timeline_edits` and leaves the pipeline in `PENDING_REVIEW` (an edit doesn't imply approval).

### 5.6 `youtube_uploader.py` (modify — the gate)
```python
def upload_video(pipeline_id: int):
    pipeline = database.get_pipeline(pipeline_id)
    if pipeline["status"] != PipelineStatus.APPROVED:
        raise PermissionError(
            f"Refusing to upload pipeline {pipeline_id}: status is "
            f"{pipeline['status']!r}, not APPROVED."
        )
    pipeline_state.transition(pipeline_id, PipelineStatus.UPLOADING)
    # ... existing resumable upload logic ...
    pipeline_state.transition(pipeline_id, PipelineStatus.UPLOADED)
```

### 5.7 Orchestrator / batch runner (modify)
Find wherever the current code chains render → upload automatically (likely in a batch/scheduler entry point) and remove the automatic upload call entirely. The batch runner's job now ends at `PENDING_REVIEW`. It should just log (and optionally raise a desktop notification, e.g. via `plyer` or a CTk toast) that N videos are waiting for review — it must never call `upload_video()` itself.

---

## 6. GUI additions (`gui.py`, CustomTkinter)

CustomTkinter has no built-in video playback or timeline widget, so be explicit about the building blocks:

- **Video preview:** use `python-vlc` (`pip install python-vlc`, requires VLC installed on the host) to embed a real player into a Tkinter frame via the frame's native window handle. This gives actual scrubbable playback, which a Canvas/thumbnail-only approach can't. Fall back to "open in system default player" as a button if VLC isn't available on a given machine.
- **Timeline widget:** a custom `tkinter.Canvas` component. Each beat renders as a colored block whose width is proportional to its duration. Support:
  - Drag-to-reorder (mouse motion + button-release rebuilds the `timeline_spec` and calls `reassemble_from_timeline`).
  - Draggable in/out handles on each block for trim (calls the same reassemble path with updated `trim_start`/`trim_end`).
  - Right-click context menu per block: "Cut this beat", "Regenerate this beat" (calls `render_single_beat`, then re-runs `reassemble_from_timeline` once the new clip is ready).
  - A waveform sparkline under each block, generated once via `pydub`/`numpy` from the beat's audio and cached as a small PNG, so it doesn't need to be recomputed on every redraw.
- **Caption editor:** a scrollable list of editable text fields, one per caption line (seeded from beat text). Saving calls `regenerate_captions`.
- **Music swap:** a dropdown listing the existing background-music asset folder, plus a preview-play button, calling `swap_background_music` on selection.

### 6.1 New tab: "Script Review"
Reached when a pipeline hits `SCRIPT_REVIEW`. Per-beat editable text box for the spoken line, read-only view of `visual_action`/`params` (edit these only if you also expose a params editor — otherwise keep them read-only to avoid producing invalid Manim inputs), a "Regenerate Beat" button, and "Approve & Render All" which calls `script_review_manager.approve_script`.

### 6.2 New tab: "Review & Approve"
Left panel: queue list of every pipeline currently in `PENDING_REVIEW` or `NEEDS_REGENERATION`, oldest first, with a colored status badge, refreshed on a polling timer (e.g. every 3-5s) since rendering runs on background threads.

Main panel, for the selected video:
- VLC-embedded preview player.
- The timeline editor described above.
- Caption editor.
- Music swap dropdown.
- Metadata fields: Title / Description / Tags / Thumbnail (pulled from LLM-suggested defaults, fully editable).
- Action buttons:
  - **Approve & Upload** — enabled only if the health check passed; calls `transition(→ APPROVED)` then `youtube_uploader.upload_video`.
  - **Reject** — opens a text box for `rejection_reason`, then a choice of "send back to Script Review" or "discard to Draft".
  - **Save Draft** — persists any edits made so far without changing status, so review can be picked up later.

### 6.3 New tab: "Logs"
Table view (a `Treeview` or `CTkTable`) with columns: timestamp, pipeline_id/topic, stage, level, duration. Filters for pipeline/topic, stage, level, and date range. Clicking a row opens a detail popup with the full message (and stack trace, if the log level is ERROR). Add an "Export to CSV" button. Add a live-tail toggle that auto-refreshes while a pipeline is actively rendering, reusing the existing `ConsoleDirector` queue pattern already in `gui.py`, scoped to the selected pipeline.

---

## 7. Concurrency notes
Every render/regenerate/reassemble call triggered from a GUI button must run on a background `threading.Thread` (matching the existing pattern), with a thread-safe queue or callback to update the review queue list and any progress indicator once the operation finishes — the Tkinter mainloop must never block. Extend the existing API-cooldown lock in `database.py` so a single-beat regeneration can't collide with the global Groq/Manim render queue used by the main batch pipeline.

---

## 8. Suggested delivery order
Given the scope, build and verify in this order rather than attempting everything as one change:

1. **Core gate + logging** — schema, `pipeline_state.py`, the hard `APPROVED`-only upload assertion, `pipeline_log` writes from every existing stage, a basic Logs tab, and a basic Review & Approve tab (VLC preview + metadata edit + Approve/Reject only, no timeline editor yet).
2. **Script review** — `SCRIPT_REVIEW` stage, `script_review_manager.py`, per-beat text editor, pre-render beat regeneration.
3. **Post-render editing tools** — trim, music swap, caption editor, single-beat regeneration after rendering.
4. **Full timeline editor** — the Canvas-based drag/reorder/cut widget with waveform previews.

Each phase should be independently testable and mergeable — don't let phase 4 block phases 1-3 from shipping.

---

## 9. New dependencies
Add to `requirements.txt`:
- `python-vlc` (video preview embedding — note this requires VLC Media Player installed on the host, not just the Python package)
- `pydub` (waveform generation, audio-only re-mixing for music swap/captions)

`ffmpeg` is presumably already a dependency via MoviePy; confirm rather than assume.

---

## 10. Acceptance checklist
- [ ] No pipeline can reach `UPLOADED` without passing through an explicit `APPROVED` transition set by a GUI button click.
- [ ] `youtube_uploader.upload_video()` raises `PermissionError` if called on a non-`APPROVED` pipeline, even if invoked directly/manually.
- [ ] Editing a beat's script pre-render only re-renders that beat, not the whole video, and not the trend-scrape/script-gen stages.
- [ ] Reordering/trimming/cutting on the timeline only re-runs MoviePy assembly, never re-invokes Manim for unaffected beats.
- [ ] Swapping music and correcting captions never re-renders visual clips.
- [ ] Every pipeline stage (trend scrape, script gen, each beat render, TTS, assembly, health check, upload) writes at least one `pipeline_log` row with a duration.
- [ ] The Logs tab filters correctly by pipeline, stage, level, and date, and exports to CSV.
- [ ] Rejecting a video with a reason correctly routes it back to either `SCRIPT_REVIEW` or `DRAFT`, per the user's choice at reject time.
- [ ] The GUI stays responsive (no frozen mainloop) during any render, regenerate, or reassemble operation.
- [ ] The batch/scheduled runner stops at `PENDING_REVIEW` and never calls upload on its own.

---

## 11. Notes for Antigravity
- Inspect the real current contents of `gui.py`, `database.py`, `video_editor.py`, `beat_renderer.py`, `storyboard_engine.py`, and `youtube_uploader.py` before writing code — the table names, function names, and GUI structure above are the intended design, not guaranteed to match existing naming. Adapt to existing conventions where they differ, and note any such deviation in a comment near the change.
- Do not remove or weaken any existing automation (trend intelligence, TTS preprocessing, health checks, API-cooldown locking) — this feature only inserts checkpoints and editing surfaces around the existing pipeline; it doesn't replace any of it.
- If something here is genuinely ambiguous and blocks progress, default to the most conservative choice (never auto-upload, always require an explicit human action) and leave a comment explaining the assumption, rather than pausing implementation.

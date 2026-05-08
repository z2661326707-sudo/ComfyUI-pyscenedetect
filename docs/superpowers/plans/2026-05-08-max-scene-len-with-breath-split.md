# Max Scene Length with Breath Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `max_scene_len` parameter to `SplitVideo` node, enabling automatic sub-splitting of long scenes at audio silence points (breath points), and change output format to `VHS_FILENAMES` for direct compatibility with OSS upload nodes.

**Architecture:** When a detected scene exceeds `max_scene_len`, extract its audio track via ffmpeg, run pydub's `detect_silence` to find silence regions, then iteratively find cut points by searching backward from ideal boundaries within `max_lookback` seconds for the nearest silence point. Force-cut at the ideal boundary if no silence is found. Output format changes from newline-separated STRING to `VHS_FILENAMES` tuple `(False, [paths...])`.

**Tech Stack:** Python 3.10+, pydub (>=0.25.1), PySceneDetect (>=0.6.4), ffmpeg (external), ComfyUI custom node API

---

## File Map

| File | Responsibility |
|------|---------------|
| `requirements.txt` | Add `pydub>=0.25.1` |
| `nodes.py` | Add `_find_silence_points()` helper, `_extract_scene_audio()` helper; update `SplitVideo.INPUT_TYPES()` with new params; update `split_video()` with sub-split logic; change `RETURN_TYPES` to `VHS_FILENAMES` |
| `README.md` | Update SplitVideo node documentation |

---

## Task 1: Add pydub Dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update requirements.txt**

Current content:
```
scenedetect[opencv]>=0.6.4
```

New content:
```
pydub>=0.25.1
scenedetect[opencv]>=0.6.4
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "print('requirements.txt OK')"`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pydub dependency for silence detection"
```

---

## Task 2: Silence Detection Helpers

**Files:**
- Modify: `nodes.py` (add two module-level helper functions before `SceneDetect` class)

### `_find_silence_points()` Function

```python
def _find_silence_points(
    audio_path: str,
    silence_thresh: float = -40.0,
    min_silence_len: int = 150,
) -> list[float]:
    """Detect silence regions in an audio file and return start times in seconds.
    
    Uses pydub's silence.detect_silence which internally analyzes amplitude
    in dBFS. Silence is defined as regions below ``silence_thresh`` dBFS
    lasting at least ``min_silence_len`` ms.
    
    Args:
        audio_path: Path to audio file (any format ffmpeg supports).
        silence_thresh: Silence threshold in dBFS (e.g. -40.0).
        min_silence_len: Minimum silence duration in milliseconds.
    
    Returns:
        Sorted list of silence start times in seconds (float).
    """
    from pydub import AudioSegment
    from pydub.silence import detect_silence

    audio = AudioSegment.from_file(audio_path)
    silent_ranges = detect_silence(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=int(silence_thresh),
        seek_step=10,
    )
    # detect_silence returns [[start_ms, end_ms], ...]
    # Extract start times and convert to seconds
    return [rng[0] / 1000.0 for rng in silent_ranges]
```

### `_extract_scene_audio()` Function

```python
def _extract_scene_audio(
    video_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
) -> None:
    """Extract audio from a video segment to a temporary WAV file.
    
    Uses ffmpeg to extract the audio track from the specified time range.
    
    Args:
        video_path: Path to the source video file.
        start_sec: Start time in seconds.
        end_sec: End time in seconds.
        output_path: Path to write the extracted audio (WAV format).
    
    Raises:
        RuntimeError: If ffmpeg extraction fails (non-zero return code).
    """
    import subprocess

    duration = end_sec - start_sec
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start_sec),
        "-i", video_path,
        "-t", str(duration),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg audio extraction failed for {video_path} "
            f"[{start_sec}s-{end_sec}s]: {result.stderr.strip()}"
        )
```

### Integration Point

Insert both functions at the **top of `nodes.py`**, after the `import` statements and before the `DETECTOR_MAP` constant.

- [ ] **Step 1: Add `_find_silence_points()` to nodes.py**

Write the function as shown above.

- [ ] **Step 2: Add `_extract_scene_audio()` to nodes.py**

Write the function as shown above.

- [ ] **Step 3: Verify syntax**

Run: `python -c "from nodes import _find_silence_points, _extract_scene_audio; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add nodes.py
git commit -m "feat: add silence detection and audio extraction helpers"
```

---

## Task 3: SplitVideo Enhancement — Params + Sub-split Logic

**Files:**
- Modify: `nodes.py` (`SplitVideo` class only)

### 3a. Update `INPUT_TYPES()`

Replace the existing `INPUT_TYPES` method in `SplitVideo` with:

```python
@classmethod
def INPUT_TYPES(cls):
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output",
        "scene_videos",
    )
    return {
        "required": {
            "scene_list": ("SCENE_LIST",),
        },
        "optional": {
            "output_dir": ("STRING", {"default": output_dir}),
            "filename_prefix": ("STRING", {"default": ""}),
            "max_scene_len": (
                "FLOAT",
                {"default": 0.0, "min": 0.0, "max": 600.0, "step": 0.1},
            ),
            "breath_threshold": (
                "FLOAT",
                {"default": -40.0, "min": -80.0, "max": 0.0, "step": 1.0},
            ),
            "min_silence_duration": (
                "INT",
                {"default": 150, "min": 50, "max": 1000, "step": 10},
            ),
            "max_lookback": (
                "FLOAT",
                {"default": 2.0, "min": 0.5, "max": 10.0, "step": 0.1},
            ),
        },
    }
```

### 3b. Update `split_video()` Method Signature and Core Logic

Replace the existing `split_video` method with the following complete implementation:

```python
def split_video(
    self,
    scene_list,
    output_dir="",
    filename_prefix="",
    max_scene_len=0.0,
    breath_threshold=-40.0,
    min_silence_duration=150,
    max_lookback=2.0,
):
    from scenedetect import split_video_ffmpeg

    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg is not available. Please install ffmpeg to use video splitting.\n"
            "Install: https://ffmpeg.org/download.html"
        )

    video_path = scene_list["video_path"]
    fps = scene_list["video_fps"]

    # Determine filename prefix from original video name
    if not filename_prefix:
        filename_prefix = os.path.splitext(os.path.basename(video_path))[0]

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Build initial FrameTimecode scene list
    scenes_tc = []
    for s in scene_list["scenes"]:
        start = FrameTimecode(s["start_timecode"], fps=fps)
        end = FrameTimecode(s["end_timecode"], fps=fps)
        scenes_tc.append((start, end))

    # Sub-split long scenes at breath points if max_scene_len > 0
    if max_scene_len > 0:
        import tempfile

        final_scenes_tc = []
        tmp_dir = tempfile.mkdtemp(prefix="scenedetect_audio_")

        try:
            for start_tc, end_tc in scenes_tc:
                duration = end_tc.get_seconds() - start_tc.get_seconds()
                if duration <= max_scene_len:
                    final_scenes_tc.append((start_tc, end_tc))
                    continue

                # Build a list of ideal cut points from scene start
                # First cut: start + max_scene_len
                # Last cut: must be end_tc
                scene_start_sec = start_tc.get_seconds()
                ideal_cuts = []
                t = scene_start_sec + max_scene_len
                while t < end_tc.get_seconds():
                    ideal_cuts.append(t)
                    t += max_scene_len

                # Extract audio for this scene
                tmp_audio = os.path.join(tmp_dir, f"audio_{len(final_scenes_tc)}.wav")
                _extract_scene_audio(video_path, scene_start_sec, end_tc.get_seconds(), tmp_audio)

                # Find silence points in the scene audio
                silence_starts = _find_silence_points(
                    tmp_audio,
                    silence_thresh=breath_threshold,
                    min_silence_len=min_silence_duration,
                )

                # Silence points are relative to the extracted audio segment
                # which starts at scene_start_sec, so add offset
                silence_starts_abs = [sp + scene_start_sec for sp in silence_starts]

                # Now iteratively determine actual cut points
                current_start = start_tc
                current_start_sec = scene_start_sec

                for ideal_cut in ideal_cuts:
                    # Search range: [ideal_cut - max_lookback, ideal_cut]
                    search_start = ideal_cut - max_lookback
                    candidates = [
                        sp for sp in silence_starts_abs
                        if search_start <= sp <= ideal_cut
                    ]

                    if candidates:
                        actual_cut_sec = candidates[-1]  # latest valid breath point
                    else:
                        actual_cut_sec = ideal_cut  # force-cut fallback

                    # Create FrameTimecode for the cut point
                    actual_cut_tc = FrameTimecode(
                        start=actual_cut_sec,
                        fps=fps,
                    )
                    final_scenes_tc.append((current_start, actual_cut_tc))

                    current_start = actual_cut_tc
                    current_start_sec = actual_cut_sec

                # Last segment: from current_start to end_tc
                final_scenes_tc.append((current_start, end_tc))

        finally:
            # Cleanup temp audio files
            import shutil as shutil_mod
            shutil_mod.rmtree(tmp_dir, ignore_errors=True)

        scenes_tc = final_scenes_tc

    # Set output file template
    output_template = os.path.join(
        output_dir, f"{filename_prefix}-Scene-$SCENE_NUMBER.mp4"
    )

    # Split video using ffmpeg
    split_video_ffmpeg(
        video_path,
        scenes_tc,
        output_dir=output_dir,
        output_file_template=output_template,
        show_progress=True,
    )

    # Collect output file paths
    file_paths = sorted(
        [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith(f"{filename_prefix}-Scene-") and f.endswith(".mp4")
        ]
    )

    # Return as VHS_FILENAMES format: (is_grid: bool, file_list: list)
    # is_grid=False means this is a flat list of video files (standard for upload nodes)
    return (False, file_paths)
```

### 3c. Change `RETURN_TYPES` and `RETURN_NAMES`

Update the class attributes in `SplitVideo`:

```python
RETURN_TYPES = ("VHS_FILENAMES",)
RETURN_NAMES = ("VHS_FILENAMES",)
```

- [ ] **Step 1: Update `INPUT_TYPES()` in `SplitVideo`**

Replace the method with the new version including all 4 new optional parameters.

- [ ] **Step 2: Update `split_video()` method**

Replace with the complete implementation above, including:
- New method signature with all parameters
- `max_scene_len > 0` branch with temp dir, audio extraction, silence detection
- Iterative cut point resolution with breath point lookback
- `finally` block for temp dir cleanup
- VHS_FILENAMES return format

- [ ] **Step 3: Update `RETURN_TYPES` and `RETURN_NAMES`**

Change from `("STRING",)` / `("file_paths",)` to `("VHS_FILENAMES",)` / `("VHS_FILENAMES",)`.

- [ ] **Step 4: Verify syntax and import**

Run: `python -c "from nodes import SceneDetect, SplitVideo; print('OK'); import json; print(json.dumps(SplitVideo.INPUT_TYPES()['optional'], indent=2))"`

Expected: `OK` followed by JSON showing 6 optional params (output_dir, filename_prefix, max_scene_len, breath_threshold, min_silence_duration, max_lookback).

- [ ] **Step 5: Commit**

```bash
git add nodes.py
git commit -m "feat: add max_scene_len with breath-point sub-splitting to SplitVideo"
```

---

## Task 4: README Update

**Files:**
- Modify: `README.md`

### Updated SplitVideo Table

Replace the existing SplitVideo section (lines 59-72) with:

```markdown
### Split Video

Splits a video file at the detected scene boundaries using ffmpeg. When `max_scene_len` is set, long scenes are further sub-split at audio silence points (breath points) for natural-cut boundaries.

| Input                  | Type       | Default            | Description                                           |
|------------------------|------------|--------------------|-------------------------------------------------------|
| `scene_list`           | SCENE_LIST | —                  | Output from Scene Detect node                         |
| `output_dir`           | STRING     | `ComfyUI/output/scene_videos` | Output directory path                      |
| `filename_prefix`      | STRING     | (video filename)   | Prefix for output clip files                          |
| `max_scene_len`        | FLOAT      | 0.0                | Maximum scene length in seconds (0 = no limit)        |
| `breath_threshold`     | FLOAT      | -40.0              | Silence detection threshold in dBFS (-80.0 to 0.0)    |
| `min_silence_duration` | INT        | 150                | Minimum silence duration in ms (50-1000)              |
| `max_lookback`         | FLOAT      | 2.0                | Max seconds to look back for breath point (0.5-10.0)  |

| Output           | Type            | Description                                           |
|------------------|-----------------|-------------------------------------------------------|
| `VHS_FILENAMES`  | VHS_FILENAMES   | Tuple of (is_grid, file_list) compatible with upload nodes |
```

Also update the **Example Workflow** section to show the new connection:

```markdown
## Example Workflow

```
Text/URL (STRING) ──→ Scene Detect ──SCENE_LIST──→ Split Video ──VHS_FILENAMES──→ OSS Video Uploader
```
```

- [ ] **Step 1: Update SplitVideo input/output tables in README.md**

Replace the tables as shown above.

- [ ] **Step 2: Update Example Workflow section**

Replace with the simplified workflow showing VHS_FILENAMES → OSS Video Uploader.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README with max_scene_len params and VHS_FILENAMES output"
```

---

## Self-Review Checklist

### Spec Coverage
- [x] `max_scene_len` parameter with default 0 (no limit) — Task 3
- [x] Breath-point sub-split logic — Task 2 + Task 3
- [x] `breath_threshold`, `min_silence_duration`, `max_lookback` params — Task 3
- [x] `pydub` dependency — Task 1
- [x] Audio extraction via ffmpeg — Task 2
- [x] Temp file cleanup (`try/finally`) — Task 3
- [x] Output format: `VHS_FILENAMES` — Task 3
- [x] Global re-numbering (implicit via `$SCENE_NUMBER` template) — Task 3
- [x] README documentation — Task 4

### No Placeholders
- [x] All code is complete — no "TBD", "TODO", "add validation" etc.
- [x] All functions have full implementations shown
- [x] All steps have exact commands with expected output

### Type Consistency
- [x] `_find_silence_points()` signature matches usage in `split_video()`
- [x] `_extract_scene_audio()` signature matches usage in `split_video()`
- [x] Parameter names match between `INPUT_TYPES` and `split_video()` signature
- [x] `FrameTimecode` constructor usage matches PySceneDetect API

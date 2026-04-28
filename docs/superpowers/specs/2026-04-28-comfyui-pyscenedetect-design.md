# ComfyUI-pyscenedetect Design Spec

**Date**: 2026-04-28
**Status**: Approved
**Source Library**: [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) (>=0.6.4)

## Overview

Wrap PySceneDetect as a ComfyUI custom node plugin that provides scene detection and video splitting capabilities. The plugin exposes two nodes: SceneDetect detects scene boundaries in a video file (supports both local paths and URLs), SplitVideo cuts the original video at those boundaries using ffmpeg, preserving audio.

## Approach

**Direct file-based detection + ffmpeg splitting**: SceneDetect uses PySceneDetect's Python API directly on video files/URLs (no dependency on VideoHelperSuite's loaded frames). SplitVideo uses PySceneDetect's `split_video_ffmpeg()` to cut the original video, preserving audio and original encoding quality. Output file paths are returned for downstream processing.

## Nodes

### Node 1: SceneDetect

| Property | Value |
|----------|-------|
| Class Name | `SceneDetect` |
| Display Name | `Scene Detect` |
| Category | `Video/SceneDetect` |
| Description | Detect scene change points in a video |

**Inputs:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `video_path` | `STRING` | `""` | Video file path or URL |
| `detector` | `COMBO` | `Content` | Detection algorithm |
| `threshold` | `FLOAT` | 27.0 | Detection sensitivity |
| `min_scene_len` | `FLOAT` | 0.5 | Minimum scene duration in seconds |

**Outputs:**

| Name | Type | Description |
|------|------|-------------|
| `SCENE_LIST` | `SCENE_LIST` | Internal scene list data (dict) for Split Video node |
| `TEXT` | `STRING` | Scene summary text (rendered when connected to a text display node) |

**Detector options and default thresholds:**

| Detector | Default Threshold |
|----------|-------------------|
| Content | 27.0 |
| Adaptive | 3.0 |
| Threshold | 12.0 |
| Histogram | 0.05 |
| Hash | 0.395 |

When the user switches the `detector` dropdown, `threshold` auto-updates to the corresponding algorithm's default value.

### Node 2: SplitVideo

| Property | Value |
|----------|-------|
| Class Name | `SplitVideo` |
| Display Name | `Split Video` |
| Category | `Video/SceneDetect` |
| Description | Split a video at detected scene boundaries |

**Inputs:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `scene_list` | `SCENE_LIST` | required | Output from Scene Detect node |
| `output_dir` | `STRING` | `{comfy_output}/scene_videos/` | Directory for split files |
| `filename_prefix` | `STRING` | `{original_name}` | Output filename prefix (auto-derived from video name if empty) |

**Outputs:**

| Name | Type | Description |
|------|------|-------------|
| `file_paths` | `STRING` | Newline-separated list of split video file paths |

## Workflow

```
Text/URL (STRING) ──→ VHS_LoadVideoPath ──IMAGE──→ (downstream processing)
                 ──→ Scene Detect ──SCENE_LIST──→ Split Video ──file_paths──→ (downstream)
```

User inputs the URL/path once via a Primitive/Text node. It fans out to both VHS_LoadVideoPath and SceneDetect. SplitVideo automatically reads the video path from SCENE_LIST — no duplicate input needed.

## Data Flow

### SCENE_LIST internal structure

Passed between nodes as a Python dict:

```python
{
    "video_path": str,
    "scenes": [
        {
            "scene_number": int,
            "start_timecode": str,    # "00:00:00.000"
            "end_timecode": str,
            "start_seconds": float,
            "end_seconds": float,
            "start_frame": int,
            "end_frame": int,
        },
    ],
    "total_scenes": int,
    "video_fps": float,
    "video_duration": float,
}
```

### Scene Detect workflow

```
video_path (STRING) input
  -> Create detector based on user selection
  -> Call scenedetect.detect() on the video file/URL
  -> Convert SceneList to internal dict structure (with video_path stored)
  -> Format TEXT output (scene summary)
  -> Return (scene_list_dict, text_string)
```

### Split Video workflow

```
SCENE_LIST input
  -> Extract video_path and scene timecodes from SCENE_LIST
  -> Check ffmpeg availability
  -> Call scenedetect.split_video_ffmpeg() to split into output_dir
  -> Collect output file paths
  -> Return (file_paths_string,)
```

## Implementation Details

1. **URL support**: `video_path` accepts both local file paths and HTTP/RTSP URLs. PySceneDetect (OpenCV) and ffmpeg both handle URLs natively.
2. **Threshold auto-switch**: `INPUT_TYPES` returns detector-specific default threshold based on `detector` selection.
3. **Split naming convention**: `{prefix}-Scene-$SCENE_NUMBER.mp4` (e.g., `myvideo-Scene-001.mp4`).
4. **ffmpeg check**: Split Video node checks `scenedetect.is_ffmpeg_available()` before execution; raises a clear error message if unavailable.
5. **Audio preservation**: Splitting is done via ffmpeg on the original file, so audio tracks are preserved in output clips.
6. **No VideoHelperSuite dependency for core logic**: The plugin does not import or depend on VideoHelperSuite internally. Users can optionally use VHS nodes in their workflow for loading split videos.

## Project Structure

```
ComfyUI-pyscenedetect/
├── __init__.py              # Plugin entry: NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
├── nodes.py                 # SceneDetect and SplitVideo node implementations
├── requirements.txt         # Python dependencies
├── README.md                # Usage docs: install, node descriptions, example workflows
└── LICENSE                  # MIT
```

| File | Responsibility |
|------|---------------|
| `__init__.py` | Register node mappings, import nodes |
| `nodes.py` | Full implementation of both node classes |
| `requirements.txt` | Declare dependencies |

## Dependencies

**requirements.txt:**
```
scenedetect[opencv]>=0.6.4
```

**External (user must install separately):**
- `ffmpeg` — required for video splitting

## Installation

Standard ComfyUI custom node installation:

```bash
cd ComfyUI/custom_nodes/
git clone <repo_url> ComfyUI-pyscenedetect
cd ComfyUI-pyscenedetect
pip install -r requirements.txt
```

Restart ComfyUI to load the plugin.

## Out of Scope

- Per-detector advanced parameters (only simplified threshold + min_scene_len)
- Video encoding parameter customization (uses ffmpeg defaults from PySceneDetect)
- Support for video backends other than OpenCV (no PyAV/MoviePy options)
- Scene image extraction (save-images)
- Scene list export formats (CSV, EDL, FCPXML, etc.)
- Direct VIDEO object construction (split files are returned as paths)

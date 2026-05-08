# ComfyUI-pyscenedetect

A ComfyUI custom node that detects scene changes in videos and splits them into clips using [PySceneDetect](https://scenedetect.com/). It features advanced **vocal separation** and **breath-point intelligent splitting** for natural, dialogue-friendly segments.

## Features

- **Scene Detection**: 5 robust algorithms (Content, Adaptive, Threshold, Histogram, Hash)
- **Intelligent Video Splitting**: Automatically splits long scenes at audio breath points (silence gaps) using `demucs` vocal separation
- **Natural Boundaries**: Cuts videos at speech pauses rather than arbitrary timestamps
- **Batch Upload Ready**: Outputs `VHS_FILENAMES` list format for direct integration with OSS/Cloud upload nodes
- **Audio Preserved**: Maintains original audio during video splitting
- **Local & URL Support**: Works with local video files and remote URLs

## Prerequisites

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [ffmpeg](https://ffmpeg.org/download.html) (required for video/audio processing)
- Python 3.9+
- **demucs** (installed via requirements.txt, ~2GB model download on first run)
- **pydub** (installed via requirements.txt, for silence detection)

## Installation

1. Navigate to your ComfyUI `custom_nodes` directory:

   ```bash
   cd ComfyUI/custom_nodes
   ```

2. Clone this repository:

   ```bash
   git clone https://github.com/your-username/ComfyUI-pyscenedetect.git
   ```

3. Install dependencies:

   ```bash
   cd ComfyUI-pyscenedetect
   pip install -r requirements.txt
   ```

4. Restart ComfyUI.

   > **Note**: On first run with `max_scene_len > 0`, the `demucs` model will be downloaded automatically (~2GB). This may take a few minutes.

## Nodes

### Scene Detect

Detects scene change points in a video file or URL.

| Input          | Type   | Default | Description                          |
|----------------|--------|---------|--------------------------------------|
| `video_path`   | STRING | `""`    | Path or URL to the video file        |
| `detector`     | COMBO  | Content | Detection algorithm                  |
| `threshold`    | FLOAT  | 27.0    | Detection sensitivity (0.0 - 100.0)  |
| `min_scene_len`| FLOAT  | 1.0     | Minimum scene length in seconds      |

| Output       | Type       | Description                          |
|--------------|------------|--------------------------------------|
| `SCENE_LIST` | SCENE_LIST | Internal scene data for Split Video  |
| `TEXT`       | STRING     | Human-readable scene summary         |

### Split Video

Splits a video file at detected scene boundaries using ffmpeg. When `max_scene_len` is enabled, long scenes are further sub-split at audio breath points for natural-cut boundaries.

**Intelligent Splitting Flow**:
1. Extract audio from the long scene
2. Separate vocals using `demucs` (removes background noise/music)
3. Detect silence points in vocals-only audio
4. Cut at the nearest breath point to the ideal interval
5. If no breath point found within lookback window, force-cut at ideal position

| Input                  | Type       | Default            | Description                                           |
|------------------------|------------|--------------------|-------------------------------------------------------|
| `scene_list`           | SCENE_LIST | —                  | Output from Scene Detect node                         |
| `output_dir`           | STRING     | `ComfyUI/output/scene_videos` | Output directory path                      |
| `filename_prefix`      | STRING     | (video filename)   | Prefix for output clip files                          |
| `max_scene_len`        | FLOAT      | 0.0                | Maximum scene length in seconds (0 = no sub-split)    |
| `breath_threshold`     | FLOAT      | -40.0              | Silence detection threshold in dBFS (-80.0 to 0.0)    |
| `min_silence_duration` | INT        | 150                | Minimum silence duration in ms (50-1000)              |
| `max_lookback`         | FLOAT      | 2.0                | Max seconds to look back for breath point (0.5-10.0)  |
| `min_segment_len`      | FLOAT      | 2.0                | Minimum segment length in seconds (0.5-60.0)          |

| Output           | Type            | Description                                           |
|------------------|-----------------|-------------------------------------------------------|
| `VHS_FILENAMES`  | VHS_FILENAMES   | List of video files for automatic iteration with upload nodes |

> **Output Note**: The node uses `OUTPUT_IS_LIST = (True,)`, enabling ComfyUI to automatically map downstream nodes (like OSS Video Uploader) over each split video file.

## Supported Detectors

| Detector   | Description                                                              |
|------------|--------------------------------------------------------------------------|
| Content    | Detects cuts by comparing differences in HSV colour space between frames |
| Adaptive   | Content-based detector that adapts threshold based on rolling average     |
| Threshold  | Compares each frame's intensity against a computed background threshold   |
| Histogram  | Compares histograms between consecutive frames                           |
| Hash       | Compares perceptual hashes (pHash) between consecutive frames            |

## Example Workflow

```
Video Path ──→ Scene Detect ──SCENE_LIST──→ Split Video ──VHS_FILENAMES──→ OSS Video Uploader
                                    ↓
                            (if max_scene_len > 0)
                                    ↓
                        Extract Audio → Demucs Vocal Separation
                                    ↓
                        Silence Detection → Intelligent Cutting
```

## Parameters Tuning Guide

- **`max_scene_len`**: Set to `0` to disable intelligent splitting and preserve original scene boundaries exactly. Typical values: `10.0`-`30.0` seconds for dialogue content.
- **`breath_threshold`**: Lower values (e.g., `-50.0`) detect quieter silences; higher values (e.g., `-20.0`) only detect loud gaps. Start with `-40.0`.
- **`min_segment_len`**: Prevents very short clips. Default `2.0s` works for most dialogue content.
- **`max_lookback`**: How far back to search for a breath point. `2.0s` is a good balance between natural cuts and staying close to target length.

## Credits

- [PySceneDetect](https://scenedetect.com/) — Python library for video scene detection
- [demucs](https://github.com/adefossez/demucs) — Music source separation using deep learning
- [pydub](https://github.com/jiaaro/pydub) — Simple audio manipulation

## Changelog

#### v0.2.1 (2026-05-08)
- **Refactored Video Split Logic**: Reorganized `split_video()` into modular private methods for better maintainability and correctness.
- **Fixed `min_segment_len` enforcement**: Corrected a logic bug where segments shorter than `min_segment_len` could still be produced. Added iterative merging to ensure all output clips meet the minimum length requirement.
- **Fixed `max_scene_len=0` behavior**: When `max_scene_len` is set to `0`, the node now strictly preserves original scene boundaries without any sub-splitting or merging intervention.
- **Fixed file collection reliability**: Replaced directory scanning with deterministic file path generation to prevent stale files from previous runs from appearing in the output list.
- **Fixed audio filename collision**: Temp audio extraction now uses unique indices to prevent file overwrites during batch processing.

# ComfyUI-pyscenedetect

A ComfyUI custom node that detects scene changes in videos and splits them into clips using [PySceneDetect](https://scenedetect.com/).

## Features

- Scene change detection with 5 algorithms
- Video splitting at scene boundaries (via ffmpeg, with audio preserved)
- Support for local files and URLs
- Detailed scene list output with timecodes, frame numbers, and durations

## Prerequisites

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [ffmpeg](https://ffmpeg.org/download.html) (required for video splitting)
- Python 3.10+

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

## Nodes

### Scene Detect

Detects scene change points in a video file or URL.

| Input          | Type   | Default | Description                          |
|----------------|--------|---------|--------------------------------------|
| `video_path`   | STRING | `""`    | Path or URL to the video file        |
| `detector`     | COMBO  | Content | Detection algorithm                  |
| `threshold`    | FLOAT  | 27.0    | Detection sensitivity (0.0 - 100.0)  |
| `min_scene_len`| FLOAT  | 0.5     | Minimum scene length in seconds      |

| Output       | Type       | Description                          |
|--------------|------------|--------------------------------------|
| `SCENE_LIST` | SCENE_LIST | Internal scene data for Split Video  |
| `TEXT`       | STRING     | Human-readable scene summary         |

### Split Video

Splits a video file at the detected scene boundaries using ffmpeg. When `max_scene_len` is set, long scenes are further sub-split at audio silence points (breath points) for natural-cut boundaries. Uses demucs for vocal separation before silence detection.

| Input                  | Type       | Default            | Description                                           |
|------------------------|------------|--------------------|-------------------------------------------------------|
| `scene_list`           | SCENE_LIST | —                  | Output from Scene Detect node                         |
| `output_dir`           | STRING     | `ComfyUI/output/scene_videos` | Output directory path                      |
| `filename_prefix`      | STRING     | (video filename)   | Prefix for output clip files                          |
| `max_scene_len`        | FLOAT      | 0.0                | Maximum scene length in seconds (0 = no limit)        |
| `breath_threshold`     | FLOAT      | -40.0              | Silence detection threshold in dBFS (-80.0 to 0.0)    |
| `min_silence_duration` | INT        | 150                | Minimum silence duration in ms (50-1000)              |
| `max_lookback`         | FLOAT      | 2.0                | Max seconds to look back for breath point (0.5-10.0)  |
| `min_segment_len`      | FLOAT      | 2.0                | Minimum segment length in seconds (0.5-60.0)          |
| *(Prerequisite)*      | —          | —                  | Requires `demucs` for vocal separation, `pydub` for silence detection |

| Output           | Type            | Description                                           |
|------------------|-----------------|-------------------------------------------------------|
| `VHS_FILENAMES`  | VHS_FILENAMES   | Tuple of (is_grid, file_list) compatible with upload nodes |

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
Text/URL (STRING) ──→ Scene Detect ──SCENE_LIST──→ Split Video ──VHS_FILENAMES──→ OSS Video Uploader
```

## Credits

- [PySceneDetect](https://scenedetect.com/) — Python library for video scene detection

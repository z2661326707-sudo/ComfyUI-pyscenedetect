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

Splits a video file at the detected scene boundaries using ffmpeg.

| Input            | Type       | Default            | Description                    |
|------------------|------------|--------------------|--------------------------------|
| `scene_list`     | SCENE_LIST | —                  | Output from Scene Detect node  |
| `output_dir`     | STRING     | `ComfyUI/output/scene_videos` | Output directory path |
| `filename_prefix`| STRING     | (video filename)   | Prefix for output clip files   |

| Output      | Type   | Description                              |
|-------------|--------|------------------------------------------|
| `file_paths`| STRING | Newline-separated paths of split clips   |

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
Text/URL (STRING) ──→ VHS_LoadVideoPath ──IMAGE──→ (downstream)
                 ──→ Scene Detect ──SCENE_LIST──→ Split Video ──file_paths──→ (downstream)
```

## Credits

- [PySceneDetect](https://scenedetect.com/) — Python library for video scene detection

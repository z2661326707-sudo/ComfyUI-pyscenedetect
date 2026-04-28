# ComfyUI-pyscenedetect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap PySceneDetect as a ComfyUI custom node plugin with two nodes: SceneDetect (detect scene boundaries) and SplitVideo (split video at detected scenes).

**Architecture:** SceneDetect uses PySceneDetect's Python API directly on video files/URLs. SplitVideo uses ffmpeg via PySceneDetect's `split_video_ffmpeg()` to cut the original video into scene segments, preserving audio. Both nodes communicate through an internal SCENE_LIST dict passed via ComfyUI's standard return mechanism.

**Tech Stack:** Python 3.10+, PySceneDetect (>=0.6.4), ComfyUI custom node API, ffmpeg (external)

---

## File Map

| File | Responsibility |
|------|---------------|
| `__init__.py` | Plugin entry point: NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, WEB_DIRECTORY |
| `nodes.py` | SceneDetect and SplitVideo node class implementations |
| `requirements.txt` | `scenedetect[opencv]>=0.6.4` |

No `video_utils.py` needed — design simplified: SceneDetect works directly on video files via PySceneDetect, no frame-level interaction with VideoHelperSuite.

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `__init__.py` (minimal, will be completed in Task 4)

- [ ] **Step 1: Create requirements.txt**

```
scenedetect[opencv]>=0.6.4
```

- [ ] **Step 2: Create minimal __init__.py**

```python
"""ComfyUI-pyscenedetect: Scene detection and video splitting using PySceneDetect."""

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
```

- [ ] **Step 3: Commit scaffold**

```bash
git add requirements.txt __init__.py
git commit -m "chore: project scaffold with requirements"
```

---

## Task 2: SceneDetect Node

**Files:**
- Create: `nodes.py`

### Detector defaults mapping

```python
DETECTOR_DEFAULTS = {
    "Content": {"class": "ContentDetector", "threshold": 27.0},
    "Adaptive": {"class": "AdaptiveDetector", "threshold": 3.0},
    "Threshold": {"class": "ThresholdDetector", "threshold": 12.0},
    "Histogram": {"class": "HistogramDetector", "threshold": 0.05},
    "Hash": {"class": "HashDetector", "threshold": 0.395},
}
```

### SceneDetect class

```python
import os
from scenedetect import (
    detect, ContentDetector, AdaptiveDetector,
    ThresholdDetector, HistogramDetector, HashDetector,
    FrameTimecode,
)

DETECTOR_MAP = {
    "Content": ContentDetector,
    "Adaptive": AdaptiveDetector,
    "Threshold": ThresholdDetector,
    "Histogram": HistogramDetector,
    "Hash": HashDetector,
}

DETECTOR_THRESHOLDS = {
    "Content": 27.0,
    "Adaptive": 3.0,
    "Threshold": 12.0,
    "Histogram": 0.05,
    "Hash": 0.395,
}


class SceneDetect:
    """Detect scene change points in a video file or URL."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"default": "", "multiline": False}),
                "detector": (list(DETECTOR_MAP.keys()), {"default": "Content"}),
                "threshold": ("FLOAT", {"default": 27.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "min_scene_len": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 60.0, "step": 0.1}),
            },
        }

    RETURN_TYPES = ("SCENE_LIST", "STRING")
    RETURN_NAMES = ("SCENE_LIST", "TEXT")
    FUNCTION = "detect_scenes"
    CATEGORY = "Video/SceneDetect"
    OUTPUT_NODE = False

    def detect_scenes(self, video_path: str, detector: str, threshold: float, min_scene_len: float):
        # Create detector with selected threshold
        detector_cls = DETECTOR_MAP[detector]
        det = detector_cls(threshold=threshold, min_scene_len=min_scene_len)

        # Run detection using PySceneDetect high-level API
        scene_list = detect(
            video_path,
            det,
            show_progress=True,
            start_in_scene=True,
        )

        # Build internal SCENE_LIST dict
        scenes = []
        for i, (start_tc, end_tc) in enumerate(scene_list):
            scenes.append({
                "scene_number": i + 1,
                "start_timecode": start_tc.get_timecode(),
                "end_timecode": end_tc.get_timecode(),
                "start_seconds": round(start_tc.seconds, 3),
                "end_seconds": round(end_tc.seconds, 3),
                "start_frame": start_tc.frame_num,
                "end_frame": end_tc.frame_num,
            })

        scene_list_data = {
            "video_path": video_path,
            "scenes": scenes,
            "total_scenes": len(scenes),
            "video_fps": scene_list[0][0].framerate if scene_list else 0.0,
            "video_duration": round(scene_list[-1][1].seconds, 3) if scene_list else 0.0,
        }

        # Format TEXT output
        lines = [f"Detected {len(scenes)} scenes"]
        lines.append(f"FPS: {scene_list_data['video_fps']}")
        lines.append(f"Duration: {scene_list_data['video_duration']}s")
        lines.append("")
        for s in scenes:
            lines.append(
                f"Scene {s['scene_number']:>3}: "
                f"{s['start_timecode']} → {s['end_timecode']} "
                f"({s['end_seconds'] - s['start_seconds']:.1f}s)"
            )
        text_output = "\n".join(lines)

        return (scene_list_data, text_output)
```

- [ ] **Step 1: Create nodes.py with SceneDetect class**

Write the complete `nodes.py` file with the SceneDetect class as shown above.

- [ ] **Step 2: Update __init__.py to register SceneDetect**

```python
"""ComfyUI-pyscenedetect: Scene detection and video splitting using PySceneDetect."""

from .nodes import SceneDetect

NODE_CLASS_MAPPINGS = {
    "SceneDetect": SceneDetect,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SceneDetect": "Scene Detect",
}
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from nodes import SceneDetect; print('OK:', SceneDetect.CATEGORY)"`

Expected: `OK: Video/SceneDetect`

- [ ] **Step 4: Commit**

```bash
git add nodes.py __init__.py
git commit -m "feat: add SceneDetect node"
```

---

## Task 3: SplitVideo Node

**Files:**
- Modify: `nodes.py` (add SplitVideo class)

### SplitVideo class

```python
class SplitVideo:
    """Split a video file at detected scene boundaries using ffmpeg."""

    @classmethod
    def INPUT_TYPES(cls):
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "output", "scene_videos"
        )
        return {
            "required": {
                "scene_list": ("SCENE_LIST",),
            },
            "optional": {
                "output_dir": ("STRING", {"default": output_dir}),
                "filename_prefix": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_paths",)
    FUNCTION = "split_video"
    CATEGORY = "Video/SceneDetect"

    def split_video(self, scene_list, output_dir="", filename_prefix=""):
        from scenedetect import split_video_ffmpeg, is_ffmpeg_available, open_video

        if not is_ffmpeg_available():
            raise RuntimeError(
                "ffmpeg is not available. Please install ffmpeg to use video splitting.\n"
                "Install: https://ffmpeg.org/download.html"
            )

        video_path = scene_list["video_path"]

        # Determine filename prefix from original video name
        if not filename_prefix:
            filename_prefix = os.path.splitext(os.path.basename(video_path))[0]

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Build FrameTimecode scene list from stored data
        fps = scene_list["video_fps"]
        scenes_tc = []
        for s in scene_list["scenes"]:
            start = FrameTimecode(s["start_timecode"], fps=fps)
            end = FrameTimecode(s["end_timecode"], fps=fps)
            scenes_tc.append((start, end))

        # Set output file template
        output_template = os.path.join(
            output_dir,
            f"{filename_prefix}-Scene-$SCENE_NUMBER.mp4"
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
        file_paths = sorted([
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith(f"{filename_prefix}-Scene-") and f.endswith(".mp4")
        ])

        file_paths_str = "\n".join(file_paths)

        return (file_paths_str,)
```

- [ ] **Step 1: Add SplitVideo class to nodes.py**

Add the SplitVideo class (shown above) to `nodes.py`, after the SceneDetect class.

- [ ] **Step 2: Update __init__.py to register SplitVideo**

```python
"""ComfyUI-pyscenedetect: Scene detection and video splitting using PySceneDetect."""

from .nodes import SceneDetect, SplitVideo

NODE_CLASS_MAPPINGS = {
    "SceneDetect": SceneDetect,
    "SplitVideo": SplitVideo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SceneDetect": "Scene Detect",
    "SplitVideo": "Split Video",
}
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from nodes import SceneDetect, SplitVideo; print('OK:', len(SplitVideo.INPUT_TYPES()['required']))"`

Expected: `OK: 1`

- [ ] **Step 4: Commit**

```bash
git add nodes.py __init__.py
git commit -m "feat: add SplitVideo node"
```

---

## Task 4: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

Content must include:
1. Plugin name and description
2. Features (scene detection, video splitting with audio)
3. Prerequisites (ffmpeg, ComfyUI-VideoHelperSuite)
4. Installation instructions
5. Node descriptions (SceneDetect inputs/outputs, SplitVideo inputs/outputs)
6. Example workflow diagram (text-based)
7. Supported detection algorithms with brief descriptions

- [ ] **Step 2: Create LICENSE (MIT)**

Standard MIT license file.

- [ ] **Step 3: Commit**

```bash
git add README.md LICENSE
git commit -m "docs: add README and MIT license"
```

---

## Task 5: Verification

- [ ] **Step 1: Verify project structure**

Run: `ls -la && echo "---" && cat requirements.txt && echo "---" && python -c "from nodes import SceneDetect, SplitVideo; print('SceneDetect CATEGORY:', SceneDetect.CATEGORY); print('SplitVideo CATEGORY:', SplitVideo.CATEGORY)"`

Expected: All files present, imports succeed, categories printed as `Video/SceneDetect`.

- [ ] **Step 2: Verify SceneDetect INPUT_TYPES structure**

Run: `python -c "from nodes import SceneDetect; import json; types = SceneDetect.INPUT_TYPES(); print(json.dumps(types, indent=2))"`

Expected: JSON showing `video_path` (STRING), `detector` (list of 5 options), `threshold` (FLOAT), `min_scene_len` (FLOAT).

- [ ] **Step 3: Verify SplitVideo INPUT_TYPES structure**

Run: `python -c "from nodes import SplitVideo; import json; types = SplitVideo.INPUT_TYPES(); print(json.dumps(types, indent=2))"`

Expected: JSON showing `scene_list` (SCENE_LIST) in required, `output_dir` and `filename_prefix` in optional.

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address verification issues"
```

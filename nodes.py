"""ComfyUI-pyscenedetect: Scene detection and video splitting using PySceneDetect."""

import os
import shutil
from scenedetect import (
    open_video,
    SceneManager,
    ContentDetector,
    AdaptiveDetector,
    ThresholdDetector,
    HistogramDetector,
    HashDetector,
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
                "threshold": (
                    "FLOAT",
                    {"default": 27.0, "min": 0.0, "max": 100.0, "step": 0.1},
                ),
                "min_scene_len": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 60.0, "step": 0.1},
                ),
            },
        }

    RETURN_TYPES = ("SCENE_LIST", "STRING")
    RETURN_NAMES = ("SCENE_LIST", "TEXT")
    FUNCTION = "detect_scenes"
    CATEGORY = "Video/SceneDetect"
    OUTPUT_NODE = False

    def detect_scenes(
        self, video_path: str, detector: str, threshold: float, min_scene_len: float
    ):
        # Open video to get FPS for frame count conversion
        video = open_video(video_path)
        fps = video.frame_rate

        # Convert min_scene_len from seconds to integer frame count
        # PySceneDetect requires int for min_scene_len to avoid internal type errors
        min_scene_frames = max(1, int(min_scene_len * fps))

        # Create detector with integer min_scene_len
        # Note: AdaptiveDetector uses 'adaptive_threshold' instead of 'threshold'
        detector_cls = DETECTOR_MAP[detector]
        if detector == "Adaptive":
            det = detector_cls(
                adaptive_threshold=threshold, min_scene_len=min_scene_frames
            )
        else:
            det = detector_cls(threshold=threshold, min_scene_len=min_scene_frames)

        # Run detection using SceneManager
        scene_manager = SceneManager()
        scene_manager.add_detector(det)
        scene_manager.detect_scenes(video, show_progress=True)
        scene_list = scene_manager.get_scene_list(start_in_scene=False)

        # Build internal SCENE_LIST dict
        scenes = []
        for i, (start_tc, end_tc) in enumerate(scene_list):
            scenes.append(
                {
                    "scene_number": i + 1,
                    "start_timecode": start_tc.get_timecode(),
                    "end_timecode": end_tc.get_timecode(),
                    "start_seconds": round(start_tc.frame_num / fps, 3),
                    "end_seconds": round(end_tc.frame_num / fps, 3),
                    "start_frame": start_tc.frame_num,
                    "end_frame": end_tc.frame_num,
                }
            )

        scene_list_data = {
            "video_path": video_path,
            "scenes": scenes,
            "total_scenes": len(scenes),
            "video_fps": fps,
            "video_duration": round(scene_list[-1][1].frame_num / fps, 3)
            if scene_list
            else 0.0,
        }

        # Format TEXT output
        lines = [f"Detected {len(scenes)} scenes"]
        lines.append(f"FPS: {scene_list_data['video_fps']}")
        lines.append(f"Duration: {scene_list_data['video_duration']}s")
        lines.append("")
        for s in scenes:
            lines.append(
                f"Scene {s['scene_number']:>3}: "
                f"{s['start_timecode']} \u2192 {s['end_timecode']} "
                f"({s['end_seconds'] - s['start_seconds']:.1f}s)"
            )
        text_output = "\n".join(lines)

        return (scene_list_data, text_output)


class SplitVideo:
    """Split a video file at detected scene boundaries using ffmpeg."""

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
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_paths",)
    FUNCTION = "split_video"
    CATEGORY = "Video/SceneDetect"

    def split_video(self, scene_list, output_dir="", filename_prefix=""):
        from scenedetect import split_video_ffmpeg

        if not shutil.which("ffmpeg"):
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

        file_paths_str = "\n".join(file_paths)

        return (file_paths_str,)

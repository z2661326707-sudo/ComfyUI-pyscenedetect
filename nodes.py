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
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=max(120, int(duration * 3)),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ffmpeg audio extraction timed out for {video_path} "
            f"[{start_sec}s-{end_sec}s]"
        )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        # Provide friendly error for no-audio videos
        if "no audio" in stderr.lower() or "stream map" in stderr.lower():
            raise RuntimeError(
                f"Video {video_path} has no audio track. "
                f"Breath-point splitting requires audio. "
                f"Set max_scene_len=0 to skip sub-splitting."
            )
        raise RuntimeError(
            f"ffmpeg audio extraction failed for {video_path} "
            f"[{start_sec}s-{end_sec}s]: {stderr}"
        )


def _separate_vocals(
    audio_path: str,
    output_dir: str,
) -> str:
    """Separate vocals from audio using demucs.

    Runs demucs CLI in ``--two-stems=vocals`` mode, which splits the input
    into ``vocals`` and ``other`` stems. Returns the path to the vocals file.

    Args:
        audio_path: Path to input audio file (any format ffmpeg supports).
        output_dir: Directory where demucs will output separated stems.

    Returns:
        Absolute path to the vocals-only audio file (WAV format).

    Raises:
        RuntimeError: If demucs is not installed or separation fails.
    """
    import subprocess
    from pathlib import Path

    if not shutil.which("demucs"):
        raise RuntimeError(
            "demucs is not available. Please install demucs to use vocal separation.\n"
            "Install: pip install demucs>=4.1.0"
        )

    if not Path(audio_path).exists():
        raise RuntimeError(
            f"Audio file not found for vocal separation: {audio_path}"
        )

    cmd = [
        "demucs",
        "--two-stems", "vocals",
        "--out", output_dir,
        "--quiet",
        audio_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"demucs vocal separation timed out for {audio_path}"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"demucs vocal separation failed: {(result.stderr or '').strip()}"
        )

    # demucs outputs to {output_dir}/htdemucs/{filename_stem}/vocals.wav
    stem_dir = Path(output_dir) / "htdemucs" / Path(audio_path).stem
    vocals_path = stem_dir / "vocals.wav"
    if not vocals_path.exists():
        # Try MP3 fallback
        vocals_path = stem_dir / "vocals.mp3"
    if not vocals_path.exists():
        raise RuntimeError(
            f"demucs completed but vocals file not found at {stem_dir}"
        )
    return str(vocals_path)


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
                "min_segment_len": (
                    "FLOAT",
                    {"default": 2.0, "min": 0.5, "max": 60.0, "step": 0.1},
                ),
            },
        }

    RETURN_TYPES = ("VHS_FILENAMES",)
    RETURN_NAMES = ("VHS_FILENAMES",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "split_video"
    CATEGORY = "Video/SceneDetect"

    def split_video(
        self,
        scene_list,
        output_dir="",
        filename_prefix="",
        max_scene_len=0.0,
        breath_threshold=-40.0,
        min_silence_duration=150,
        max_lookback=2.0,
        min_segment_len=2.0,
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

            with tempfile.TemporaryDirectory(prefix="scenedetect_audio_") as tmp_dir:
                for start_tc, end_tc in scenes_tc:
                    duration = end_tc.get_seconds() - start_tc.get_seconds()
                    if duration <= max_scene_len:
                        final_scenes_tc.append((start_tc, end_tc))
                        continue

                    # Extract audio for this scene
                    scene_start_sec = start_tc.get_seconds()
                    tmp_audio = os.path.join(tmp_dir, f"audio_{len(final_scenes_tc)}.wav")
                    _extract_scene_audio(video_path, scene_start_sec, end_tc.get_seconds(), tmp_audio)

                    # Separate vocals using demucs for better breath-point detection
                    vocals_path = _separate_vocals(tmp_audio, tmp_dir)

                    # Find silence points in the vocals-only audio
                    silence_starts = _find_silence_points(
                        vocals_path,
                        silence_thresh=breath_threshold,
                        min_silence_len=min_silence_duration,
                    )

                    # Silence points are relative to the extracted audio segment
                    # which starts at scene_start_sec, so add offset
                    silence_starts_abs = [sp + scene_start_sec for sp in silence_starts]

                    # Dynamically recalculate ideal cut points after each actual cut
                    # to prevent segments exceeding max_scene_len
                    current_start = start_tc
                    current_start_sec = scene_start_sec

                    while True:
                        # Calculate next ideal cut from current position
                        next_ideal_sec = current_start_sec + max_scene_len
                        if next_ideal_sec >= end_tc.get_seconds():
                            break  # Last segment will go to end_tc

                        # Search range: [next_ideal - max_lookback, next_ideal]
                        search_start = next_ideal_sec - max_lookback
                        candidates = [
                            sp for sp in silence_starts_abs
                            if search_start <= sp <= next_ideal_sec
                        ]

                        if candidates:
                            actual_cut_sec = candidates[-1]  # latest valid breath point
                        else:
                            actual_cut_sec = next_ideal_sec  # force-cut fallback

                        # Safety clamp: ensure cut is not before current_start
                        actual_cut_sec = max(actual_cut_sec, current_start_sec + 0.1)

                        # Minimum segment length check:
                        # If the resulting segment would be too short, skip this cut point
                        # and continue searching from the next ideal position.
                        if (actual_cut_sec - current_start_sec) < min_segment_len:
                            # Jump to next ideal position and continue loop
                            current_start_sec = next_ideal_sec
                            continue

                        # Create FrameTimecode for the cut point
                        actual_cut_tc = FrameTimecode(
                            timecode=actual_cut_sec,
                            fps=fps,
                        )
                        final_scenes_tc.append((current_start, actual_cut_tc))

                        current_start = actual_cut_tc
                        current_start_sec = actual_cut_sec

                    # Last segment: from current_start to end_tc
                    final_scenes_tc.append((current_start, end_tc))

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

        # Build a list of single-file VHS_FILENAMES tuples for ComfyUI list mapping
        # ComfyUI will automatically map downstream nodes (like OSS Video Uploader)
        # over this list, executing them once per file.
        single_file_outputs = [(False, [fp]) for fp in file_paths]

        # ComfyUI expects a 1-tuple for single output. OUTPUT_IS_LIST tells it to iterate.
        return (single_file_outputs,)

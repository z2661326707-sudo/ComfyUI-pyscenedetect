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

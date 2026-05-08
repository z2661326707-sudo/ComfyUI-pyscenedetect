# Plan: Refactor Video Split Logic — Enforce min_segment_len & Skip Unnecessary Sub-Split

**Created**: 2026-05-08
**Status**: In Progress
**Progress**: 0

## Problem

Two bugs in `SplitVideo.split_video()` (nodes.py, lines 333-482):

1. **min_segment_len not enforced** — scenes shorter than `min_segment_len` appear in output despite the parameter being set (e.g., 3s setting produces 1s clips). Root cause: hardcoded `0.1s` floor on line 421 runs *before* the `min_segment_len` check, and the tail-segment merge logic (lines 441-449) has a backtracking flaw that can produce undersized segments.

2. **Unnecessary sub-split on short scenes** — while the code at lines 376-380 does skip subsplit when `duration <= max_scene_len`, users report short scenes still undergoing audio extraction. Likely a non-issue if logic is correct, but the monolithic structure makes it hard to verify and debug.

## Approach (Plan B)

Refactor `split_video()` by extracting private methods with single responsibilities. All existing parameters, API, and behavior are preserved. No new dependencies.

### New Method Structure

All private methods on `SplitVideo` class:

```
split_video() — main orchestrator (slimmed down)
├── _build_scene_timecodes() — reconstruct FrameTimecode pairs from SCENE_LIST
├── _needs_subsplit(scene_start_sec, scene_end_sec, max_scene_len) — bool
├── _candidate_cuts_for_scene(scene_start_sec, scene_end_sec, ...) — list[float]
│   └── uses existing helpers: _extract_scene_audio, _separate_vocals, _find_silence_points
├── _filter_cuts_with_min_len(candidates, start_sec, end_sec, min_segment_len) — list[float]
│   └── greedy approach: iterate candidate cut points, keep only those where
│       (cut_sec - segment_start_sec) >= min_segment_len
├── _merge_short_segments(scenes_tc, min_segment_len) — list[(FrameTimecode, FrameTimecode)]
│   └── global post-processing: iterate output segments, merge any segment below
│       min_segment_len into the larger of (previous, next) neighbor
└── split_video_ffmpeg() — existing call, unchanged
```

### Key Logic Changes

#### `_filter_cuts_with_min_len` (replaces current lines 405-434)

```python
def _filter_cuts_with_min_len(candidates, start_sec, end_sec, min_segment_len):
    """Greedy filter: keep cut points that maintain minimum segment length."""
    filtered = []
    segment_start = start_sec
    for cut_sec in candidates:
        if (cut_sec - segment_start) >= min_segment_len:
            filtered.append(cut_sec)
            segment_start = cut_sec
    return filtered
```

This replaces the confusing `while True` + `next_ideal_sec` + `actual_cut_sec = max(..., +0.1)` + skip/continue logic.

#### `_merge_short_segments` (replaces current lines 441-449)

```python
def _merge_short_segments(scenes_tc, min_segment_len):
    """Post-process: merge undersized segments into neighbor."""
    if len(scenes_tc) <= 1:
        return scenes_tc

    fps = scenes_tc[0][0].get_fps()
    merged = []
    i = 0
    while i < len(scenes_tc):
        start, end = scenes_tc[i]
        dur = end.get_seconds() - start.get_seconds()
        if dur >= min_segment_len:
            merged.append((start, end))
            i += 1
        else:
            # Merge with previous or next segment
            if merged:
                prev_start, _ = merged[-1]
                merged[-1] = (prev_start, end)  # merge into previous
            elif i + 1 < len(scenes_tc):
                _, next_end = scenes_tc[i + 1]
                merged.append((start, next_end))  # merge into next
                i += 1
            else:
                # Single undersized segment — keep it (nothing to merge with)
                merged.append((start, end))
                i += 1
    return merged
```

#### Main `split_video()` (simplified)

```python
def split_video(self, scene_list, output_dir="", filename_prefix="", ...):
    # 1. Validate ffmpeg (unchanged)
    # 2. Build initial scenes_tc
    scenes_tc = self._build_scene_timecodes(scene_list)

    # 3. Sub-split long scenes if needed
    if max_scene_len > 0:
        final_scenes_tc = []
        with tempfile.TemporaryDirectory(...) as tmp_dir:
            for start_tc, end_tc in scenes_tc:
                if not self._needs_subsplit(...):
                    final_scenes_tc.append((start_tc, end_tc))
                    continue

                # Extract audio, separate vocals, find silence (unchanged helpers)
                silence_points = ...

                # Generate ideal cut points from ideal intervals + silence lookback
                candidates = self._candidate_cuts_for_scene(...)

                # Filter candidates to respect min_segment_len
                filtered = self._filter_cuts_with_min_len(
                    candidates, start_sec, end_sec, min_segment_len
                )

                # Build sub-segments from filtered cuts
                sub_segs = self._build_sub_segments(start_tc, end_tc, filtered, fps)
                final_scenes_tc.extend(sub_segs)

        scenes_tc = final_scenes_tc

    # 4. Global post-process: enforce min_segment_len
    scenes_tc = self._merge_short_segments(scenes_tc, min_segment_len)

    # 5. Call split_video_ffmpeg (unchanged)
    # 6. Collect outputs (unchanged)
```

## Files to Modify

| File | Change |
|------|--------|
| `nodes.py` | Refactor `SplitVideo.split_video()` + add 5 new private methods |

## What NOT to Change

- `SceneDetect` class (unchanged)
- `INPUT_TYPES`, `RETURN_TYPES`, `FUNCTION`, `CATEGORY` (API contract)
- Existing helper functions: `_find_silence_points`, `_extract_scene_audio`, `_separate_vocals`
- `split_video_ffmpeg` call and its parameters
- Output format (`VHS_FILENAMES`)

## Acceptance Criteria

- [ ] No output segment shorter than `min_segment_len` (even with edge cases like tail segments)
- [ ] Scenes ≤ `max_scene_len` pass through directly without audio extraction/sub-split
- [ ] All existing parameters produce identical output for cases that previously worked correctly
- [ ] Code passes basic syntax check (no import errors)

## Evidence Required

- [ ] `python -c "import nodes; print('OK')"` — import test
- [ ] Manual verification of the two logic paths (short scene skip, min_segment_len enforcement)

## Residual Findings

_None yet._

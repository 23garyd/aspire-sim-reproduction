"""D405 depth-camera capture seam. D405Camera defers pyrealsense2 (imported inside
connect()/capture()) so this module imports with no pyrealsense2. FakeD405 returns an
injected frame for CI. The exact stream/alignment config is confirmed on-bench."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from robot_b601.perception import CameraIntrinsics


@dataclass
class D405Frame:
    color: np.ndarray
    depth: np.ndarray
    intrinsics: CameraIntrinsics


class FakeD405:
    """Deterministic camera for CI: capture() returns the injected frame."""

    def __init__(self, frame: D405Frame):
        self._frame = frame

    def connect(self):
        pass

    def capture(self) -> D405Frame:
        return self._frame

    def close(self):
        pass


class D405Camera:
    """Live D405 (on-bench). pyrealsense2 is imported in connect(); confirm the stream and
    depth-alignment config against the D405 on the bench."""

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30):
        self._w, self._h, self._fps = width, height, fps
        self._pipe = None
        self._intr = None

    def connect(self):
        import pyrealsense2 as rs
        self._pipe = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.color, self._w, self._h, rs.format.bgr8, self._fps)
        cfg.enable_stream(rs.stream.depth, self._w, self._h, rs.format.z16, self._fps)
        profile = self._pipe.start(cfg)
        v = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
        self._intr = CameraIntrinsics(v.fx, v.fy, v.ppx, v.ppy)

    def capture(self) -> D405Frame:
        if self._pipe is None:
            raise RuntimeError("D405Camera.connect() must be called before capture()")
        frames = self._pipe.wait_for_frames()
        color = np.asanyarray(frames.get_color_frame().get_data())
        depth = np.asanyarray(frames.get_depth_frame().get_data())
        return D405Frame(color, depth, self._intr)

    def close(self):
        if self._pipe is not None:
            self._pipe.stop()
            self._pipe = None

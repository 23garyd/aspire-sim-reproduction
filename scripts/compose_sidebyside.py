#!/usr/bin/env python3
"""Compose two rollout mp4s into one labeled side-by-side before/after clip.
Pads the shorter clip by freezing its last frame so both play to the same length.
No system ffmpeg needed (imageio bundles it; cv2 for compositing)."""
import argparse

import cv2
import imageio
import numpy as np


def read_frames(path):
    r = imageio.get_reader(path, format="FFMPEG")
    frames = [np.asarray(f)[..., :3] for f in r]
    r.close()
    return frames


def label(frames, title, subtitle, bar_color):
    out = []
    for f in frames:
        f = np.ascontiguousarray(f)
        h, w = f.shape[:2]
        cv2.rectangle(f, (0, 0), (w, 34), bar_color, -1)
        cv2.putText(f, title, (10, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(f, subtitle, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                    (235, 235, 235), 1, cv2.LINE_AA)
        out.append(f)
    return out


def pad_to(frames, n):
    if len(frames) >= n:
        return frames[:n]
    return frames + [frames[-1]] * (n - len(frames))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", required=True)
    ap.add_argument("--right", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--hold", type=int, default=30,
                    help="extra frames freezing the final state")
    args = ap.parse_args()

    left = read_frames(args.left)
    right = read_frames(args.right)
    # match heights (same env → same size, but be safe)
    h = min(left[0].shape[0], right[0].shape[0])

    def fit(fr):
        return [cv2.resize(f, (int(f.shape[1] * h / f.shape[0]), h)) for f in fr]

    left, right = fit(left), fit(right)
    left = label(left, "BASELINE (CaP-Agent0)", "reward 0.01  -  air grasp, no lift",
                 (40, 40, 150))
    right = label(right, "ASPIRE (rep1 winner)", "reward 1.00  -  grasps + lifts pot",
                  (40, 120, 40))

    n = max(len(left), len(right)) + args.hold
    left, right = pad_to(left, n), pad_to(right, n)

    sep = np.full((h, 4, 3), 255, np.uint8)
    with imageio.get_writer(args.out, fps=args.fps, format="FFMPEG",
                            codec="libx264") as w:
        for lf, rf in zip(left, right):
            w.append_data(np.ascontiguousarray(np.hstack([lf, sep, rf])))
    print(f"WROTE {args.out} ({n} frames, {args.fps} fps)")


if __name__ == "__main__":
    main()

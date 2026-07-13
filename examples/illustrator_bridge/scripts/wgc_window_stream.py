from __future__ import annotations

import argparse
import ctypes
import json
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from dataclasses import dataclass

import cv2
import numpy as np
from windows_cap import WindowCapture


@dataclass(frozen=True)
class WindowTarget:
    title: str
    class_name: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream one Illustrator window through Windows.Graphics.Capture."
    )
    parser.add_argument("--proxy-url", default="http://127.0.0.1:8972")
    parser.add_argument("--title-contains", default="Illustrator")
    parser.add_argument("--fps", type=float, default=3.0)
    parser.add_argument("--jpeg-quality", type=int, default=72)
    parser.add_argument("--max-width", type=int, default=1440)
    parser.add_argument("--max-frames", type=int, default=0, help="0 means continuous.")
    parser.add_argument("--soft-exit", action="store_true")
    return parser.parse_args()


def find_window(title_contains: str) -> WindowTarget | None:
    user32 = ctypes.windll.user32
    matches: list[WindowTarget] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        title = title_buffer.value
        if title_contains.casefold() not in title.casefold():
            return True
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, 256)
        matches.append(WindowTarget(title=title, class_name=class_buffer.value))
        return True

    user32.EnumWindows(callback, 0)
    if not matches:
        return None
    matches.sort(key=lambda item: ("Adobe Illustrator" not in item.title, len(item.title)))
    return matches[0]


def encode_frame(
    raw: bytes, width: int, height: int, max_width: int, quality: int
) -> tuple[bytes, int, int]:
    expected = width * height * 4
    if width <= 0 or height <= 0 or len(raw) < expected:
        raise ValueError("invalid_wgc_frame")
    bgra = np.frombuffer(raw, dtype=np.uint8, count=expected).reshape((height, width, 4))
    bgr = cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
    if max_width > 0 and width > max_width:
        scale = max_width / width
        width, height = max_width, max(1, round(height * scale))
        bgr = cv2.resize(bgr, (width, height), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("jpeg_encode_failed")
    return encoded.tobytes(), width, height


def post_frame(proxy_url: str, jpeg: bytes, width: int, height: int) -> None:
    request = urllib.request.Request(
        proxy_url.rstrip("/") + "/capture/frame",
        data=jpeg,
        method="POST",
        headers={
            "Content-Type": "image/jpeg",
            "X-StarBridge-Capture-Target": "illustrator-window",
            "X-Frame-Width": str(width),
            "X-Frame-Height": str(height),
        },
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        if response.status != 202:
            raise RuntimeError(f"proxy_rejected_frame:{response.status}")


def run(args: argparse.Namespace) -> dict:
    if not 0.5 <= args.fps <= 5.0:
        raise ValueError("fps must be between 0.5 and 5")
    if not 30 <= args.jpeg_quality <= 90:
        raise ValueError("jpeg-quality must be between 30 and 90")
    target = find_window(args.title_contains)
    if target is None:
        raise RuntimeError("illustrator_window_not_found")
    capture = WindowCapture(target.title, target.class_name or None)
    capture.start_capture()
    interval = 1.0 / args.fps
    sent = 0
    started = time.monotonic()
    while args.max_frames <= 0 or sent < args.max_frames:
        frame_started = time.monotonic()
        raw = capture.next()
        width, height = map(int, capture.client_size)
        jpeg, output_width, output_height = encode_frame(
            raw, width, height, args.max_width, args.jpeg_quality
        )
        post_frame(args.proxy_url, jpeg, output_width, output_height)
        sent += 1
        remaining = interval - (time.monotonic() - frame_started)
        if remaining > 0:
            time.sleep(remaining)
    return {
        "ok": True,
        "capture_api": "Windows.Graphics.Capture",
        "target": "illustrator-window",
        "frames_sent": sent,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "fps_limit": args.fps,
        "writes_files": False,
    }


def main() -> None:
    args = parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False))
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "capture_api": "Windows.Graphics.Capture",
                    "target": "illustrator-window",
                    "error": type(error).__name__,
                    "message": str(error),
                },
                ensure_ascii=False,
            )
        )
        if not args.soft_exit:
            raise SystemExit(1) from error


if __name__ == "__main__":
    main()

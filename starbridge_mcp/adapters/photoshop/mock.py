from __future__ import annotations

from typing import Any


def mock_document() -> dict[str, Any]:
    return {
        "name": "sandbox_mock_document",
        "width": 1440,
        "height": 960,
        "resolution": 72,
        "mode": "RGB",
        "bits_per_channel": 8,
        "layer_count": 5,
        "color_profile": "sRGB IEC61966-2.1",
    }


def mock_layers() -> list[dict[str, Any]]:
    return [
        {"id": "group-hero", "name": "Hero", "kind": "group", "depth": 0, "visible": True, "locked": False, "opacity": 100},
        {"id": "layer-bg", "name": "Background", "kind": "pixel", "depth": 1, "visible": True, "locked": True, "opacity": 100},
        {"id": "layer-subject", "name": "Subject", "kind": "smartObject", "depth": 1, "visible": True, "locked": False, "opacity": 100},
        {"id": "layer-copy", "name": "Subject Mask", "kind": "mask", "depth": 1, "visible": True, "locked": False, "opacity": 100},
        {"id": "layer-text", "name": "Title", "kind": "text", "depth": 0, "visible": True, "locked": False, "opacity": 92},
    ]


def mock_probe() -> dict[str, Any]:
    return {
        "photoshop_available": False,
        "com_available": False,
        "uxp_available": False,
        "node_proxy_available": False,
        "fallback_available": True,
        "warnings": ["Using mock bridge; no live Photoshop session was queried."],
    }

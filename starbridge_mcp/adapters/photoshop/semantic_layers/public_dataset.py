from __future__ import annotations

import hashlib
import html
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PUBLIC_DATASET_REQUEST_SCHEMA = "starbridge.public_image_dataset_request.v1"
PUBLIC_DATASET_SCHEMA = "starbridge.public_image_dataset.v1"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "StarBridge-public-dataset/1.0 "
    "(https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software; "
    "license-verified local research)"
)
_LICENSE_FAMILIES = {"public_domain", "cc0", "cc_by", "cc_by_sa"}
_IMAGE_FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "TIFF": ".tif",
}


def _plain_text(value: str, maximum: int = 256) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", without_tags).strip()[:maximum]


def _license_family(short_name: str) -> str | None:
    lowered = short_name.casefold().replace("-", " ")
    if "cc0" in lowered or "cc zero" in lowered:
        return "cc0"
    if "public domain" in lowered or lowered.strip() in {"pdm", "pd"}:
        return "public_domain"
    if "cc by sa" in lowered:
        return "cc_by_sa"
    if "cc by" in lowered:
        return "cc_by"
    return None


def load_public_dataset_request(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Public dataset request must be an object")
    if payload.get("schema_version") != PUBLIC_DATASET_REQUEST_SCHEMA:
        raise ValueError("Unsupported public dataset request schema_version")
    if set(payload) != {"schema_version", "provider", "max_width", "items"}:
        raise ValueError("Public dataset request fields do not match the allowlist")
    if payload.get("provider") != "wikimedia_commons":
        raise ValueError("Only wikimedia_commons is supported")
    max_width = int(payload.get("max_width", 0))
    if not 320 <= max_width <= 2048:
        raise ValueError("Public dataset max_width must be between 320 and 2048")
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 32:
        raise ValueError("Public dataset request must contain 1 to 32 items")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "id",
            "file_title",
            "expected_license_family",
            "use_case",
        }:
            raise ValueError("Public dataset item fields do not match the allowlist")
        item_id = str(item.get("id") or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", item_id) or item_id in seen:
            raise ValueError("Public dataset item id must be unique and filesystem-safe")
        seen.add(item_id)
        title = str(item.get("file_title") or "")
        if not title.startswith("File:") or len(title) > 256:
            raise ValueError("Public dataset file_title must be an explicit Commons File title")
        if item.get("expected_license_family") not in _LICENSE_FAMILIES:
            raise ValueError("Public dataset expected_license_family is not allowlisted")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", str(item.get("use_case") or "")):
            raise ValueError("Public dataset use_case must be a safe enum-like value")
    return payload


def _open_with_retry(request: urllib.request.Request, *, timeout: int) -> Any:
    for attempt in range(3):
        try:
            return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 503} or attempt == 2:
                raise
            try:
                retry_after = int(exc.headers.get("Retry-After") or 2**attempt)
            except ValueError:
                retry_after = 2**attempt
            time.sleep(max(1, min(retry_after, 5)))
    raise RuntimeError("Unreachable retry state")


def _fetch_commons_metadata(titles: list[str], max_width: int) -> dict[str, dict[str, Any]]:
    if not titles or len(titles) > 8:
        raise ValueError("Commons metadata requests support 1 to 8 titles per batch")
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size",
            "iiurlwidth": str(max_width),
            "titles": "|".join(titles),
            "maxlag": "5",
        }
    )
    request = urllib.request.Request(
        f"{COMMONS_API}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with _open_with_retry(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pages = payload.get("query", {}).get("pages", [])
    records: dict[str, dict[str, Any]] = {}
    for page in pages:
        if page.get("missing") is True:
            raise ValueError("Commons file title was not found")
        image_info = page.get("imageinfo", [])
        if len(image_info) != 1:
            raise ValueError("Commons did not return one imageinfo record")
        records[str(page.get("title") or "")] = image_info[0]
    if set(records) != set(titles):
        raise ValueError("Commons metadata response did not match every requested title")
    return records


def _download_public_bytes(url: str, maximum_bytes: int = 20 * 1024 * 1024) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org":
        raise ValueError("Public dataset download URL is not allowlisted")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    with _open_with_retry(request, timeout=60) as response:
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > maximum_bytes:
            raise ValueError("Public image exceeds the download size limit")
        data = response.read(maximum_bytes + 1)
    if len(data) > maximum_bytes:
        raise ValueError("Public image exceeds the download size limit")
    return data


def acquire_public_dataset(
    request_path: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    from PIL import Image

    request_payload = load_public_dataset_request(request_path)
    root = Path(output_root).expanduser().resolve()
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    metadata_by_title: dict[str, dict[str, Any]] = {}
    titles = [str(item["file_title"]) for item in request_payload["items"]]
    for start in range(0, len(titles), 8):
        metadata_by_title.update(
            _fetch_commons_metadata(titles[start : start + 8], int(request_payload["max_width"]))
        )
    for item in request_payload["items"]:
        metadata = metadata_by_title[str(item["file_title"])]
        extmetadata = metadata.get("extmetadata", {})
        license_short_name = _plain_text(
            str(extmetadata.get("LicenseShortName", {}).get("value") or "")
        )
        resolved_family = _license_family(license_short_name)
        if resolved_family != item["expected_license_family"]:
            raise ValueError(f"License verification failed for public dataset item {item['id']!r}")
        download_url = str(metadata.get("thumburl") or metadata.get("url") or "")
        data = _download_public_bytes(download_url)
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
        extension = _IMAGE_FORMAT_EXTENSIONS.get(image_format)
        if extension is None:
            raise ValueError("Public dataset image format is not supported")
        relative_path = Path(f"assets/{item['id']}{extension}")
        destination = root / relative_path
        destination.write_bytes(data)
        source_page = "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(
            str(item["file_title"]).replace(" ", "_"), safe=":()_,-"
        )
        records.append(
            {
                "id": item["id"],
                "use_case": item["use_case"],
                "local_asset": relative_path.as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "width": width,
                "height": height,
                "format": image_format,
                "source_page": source_page,
                "download_url": download_url,
                "license_family": resolved_family,
                "license_short_name": license_short_name,
                "license_url": str(extmetadata.get("LicenseUrl", {}).get("value") or source_page)[
                    :512
                ],
                "artist": _plain_text(str(extmetadata.get("Artist", {}).get("value") or "unknown")),
                "attribution": _plain_text(str(extmetadata.get("Credit", {}).get("value") or "")),
            }
        )
    report = {
        "schema_version": PUBLIC_DATASET_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "provider": "wikimedia_commons",
        "item_count": len(records),
        "license_verified": True,
        "private_paths_recorded": False,
        "items": records,
    }
    report_path = root / "dataset_manifest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**report, "report_path": str(report_path)}

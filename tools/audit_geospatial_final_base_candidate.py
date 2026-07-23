#!/usr/bin/env python3
"""Audit the current rendered map asset without promoting it as the final base.

The audit is intentionally non-destructive. It reads the configured WebP candidate,
extracts container dimensions, records a content hash, verifies the frontend reference,
and updates the geospatial progress ledger while keeping pixel calibration blocked until
source authorization, the final crop, and the overlay origin are explicitly fixed.
"""
from __future__ import annotations

import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRIGGER = ROOT / "data/geospatial/geospatial-final-base-candidate-trigger.json"
REPORT = ROOT / "data/geospatial/geospatial-final-base-candidate-audit.json"
PROGRESS = ROOT / "data/geospatial/geospatial-progress.json"
APP = ROOT / "app.js"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def u24le(data: bytes) -> int:
    if len(data) != 3:
        raise ValueError("u24le requires exactly three bytes")
    return data[0] | (data[1] << 8) | (data[2] << 16)


def parse_webp_dimensions(data: bytes) -> dict[str, Any]:
    if len(data) < 20 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise RuntimeError("candidate is not a valid RIFF WebP container")

    offset = 12
    chunks: list[str] = []
    width: int | None = None
    height: int | None = None
    alpha: bool | None = None
    animated = False
    dimension_chunk: str | None = None

    while offset + 8 <= len(data):
        fourcc = data[offset : offset + 4]
        size = struct.unpack_from("<I", data, offset + 4)[0]
        start = offset + 8
        end = start + size
        if end > len(data):
            raise RuntimeError(f"truncated WebP chunk {fourcc!r}")
        payload = data[start:end]
        name = fourcc.decode("ascii", errors="replace")
        chunks.append(name)

        if fourcc == b"VP8X":
            if len(payload) < 10:
                raise RuntimeError("invalid VP8X chunk")
            flags = payload[0]
            alpha = bool(flags & 0x10)
            animated = bool(flags & 0x02)
            width = 1 + u24le(payload[4:7])
            height = 1 + u24le(payload[7:10])
            dimension_chunk = "VP8X"
        elif fourcc == b"VP8 " and width is None:
            marker = payload.find(b"\x9d\x01\x2a")
            if marker < 0 or marker + 7 > len(payload):
                raise RuntimeError("VP8 frame header not found")
            width = struct.unpack_from("<H", payload, marker + 3)[0] & 0x3FFF
            height = struct.unpack_from("<H", payload, marker + 5)[0] & 0x3FFF
            alpha = False
            dimension_chunk = "VP8"
        elif fourcc == b"VP8L" and width is None:
            if len(payload) < 5 or payload[0] != 0x2F:
                raise RuntimeError("invalid VP8L frame header")
            b1, b2, b3, b4 = payload[1:5]
            width = 1 + (((b2 & 0x3F) << 8) | b1)
            height = 1 + (((b4 & 0x0F) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))
            alpha = bool(b4 & 0x10)
            dimension_chunk = "VP8L"

        offset = end + (size & 1)

    if width is None or height is None:
        raise RuntimeError("WebP dimensions could not be decoded")

    return {
        "format": "webp",
        "container": "RIFF/WEBP",
        "dimensionChunk": dimension_chunk,
        "width": width,
        "height": height,
        "aspectRatio": round(width / height, 8),
        "isSquare": width == height,
        "hasAlpha": alpha,
        "animated": animated,
        "chunks": chunks,
    }


def main() -> int:
    trigger = load_json(TRIGGER)
    candidate = trigger["candidate"]
    relative_path = candidate["path"]
    candidate_path = ROOT / relative_path
    if not candidate_path.is_file():
        raise RuntimeError(f"candidate file does not exist: {relative_path}")

    raw = candidate_path.read_bytes()
    image = parse_webp_dimensions(raw)
    sha256 = hashlib.sha256(raw).hexdigest()

    expected_width = int(candidate["expectedWidth"])
    expected_height = int(candidate["expectedHeight"])
    expected_format = candidate["expectedFormat"].lower()
    app_source = APP.read_text(encoding="utf-8")
    renderer_asset_reference = f"state.image.src='{relative_path}'"
    renderer_size_reference = str(expected_width)

    gates = {
        "candidateFileExists": True,
        "candidateFormatMatches": image["format"] == expected_format,
        "candidateDimensionsMatchDeclaredCurrentRenderer": (
            image["width"] == expected_width and image["height"] == expected_height
        ),
        "frontendReferencesCandidate": renderer_asset_reference in app_source,
        "frontendContainsDeclaredDimension": renderer_size_reference in app_source,
        "sourceAuthorizationFixed": trigger["authorization"]["status"] == "approved-and-recorded",
        "finalCropFixed": trigger["crop"]["status"] == "fixed",
        "overlayOriginFixed": trigger["overlayOrigin"]["status"] == "fixed",
        "finalBaseApproved": bool(candidate.get("finalBaseApproved", False)),
    }

    hard_fail_gates = {
        key: gates[key]
        for key in (
            "candidateFileExists",
            "candidateFormatMatches",
            "candidateDimensionsMatchDeclaredCurrentRenderer",
            "frontendReferencesCandidate",
            "frontendContainsDeclaredDimension",
        )
    }
    if not all(hard_fail_gates.values()):
        raise RuntimeError(f"current render-base audit failed: {hard_fail_gates}")

    blocking_items: list[str] = []
    if not gates["sourceAuthorizationFixed"]:
        blocking_items.append("final base source authorization and provenance are not approved")
    if not gates["finalCropFixed"]:
        blocking_items.append("final base crop rectangle is not fixed")
    if not gates["overlayOriginFixed"]:
        blocking_items.append("overlay pixel origin is not fixed")
    if not gates["finalBaseApproved"]:
        blocking_items.append("current render asset has not been approved as the final original ultra-HD base")

    status = "final-base-ready" if not blocking_items else "current-render-base-audited-final-base-blocked"
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "status": status,
        "stage": "final-original-ultra-hd-base-candidate-audit",
        "mode": trigger["mode"],
        "candidate": {
            "path": relative_path,
            "role": candidate["role"],
            "sizeBytes": len(raw),
            "sha256": sha256,
            **image,
        },
        "rendererContract": {
            "sourcePath": "app.js",
            "assetReferenceVerified": gates["frontendReferencesCandidate"],
            "declaredWidth": expected_width,
            "declaredHeight": expected_height,
            "dimensionReferenceVerified": gates["frontendContainsDeclaredDimension"],
            "coordinateConvention": "atlas normalized coordinates multiplied by declared square-map size",
        },
        "authorization": trigger["authorization"],
        "crop": trigger["crop"],
        "overlayOrigin": trigger["overlayOrigin"],
        "gates": gates,
        "blockingItems": blocking_items,
        "nextAction": (
            "approve and record final source, fix crop rectangle and overlay origin, then measure 24 control pixels"
            if blocking_items
            else "measure 24 control pixels and fit the first accepted transform model"
        ),
        "safety": {
            "candidatePixelsModified": False,
            "pixelCoordinatesInvented": False,
            "cropInvented": False,
            "transformClaimed": False,
            "finalBaseClaimed": status == "final-base-ready",
        },
    }
    write_json(REPORT, report)

    progress = load_json(PROGRESS)
    if progress.get("status") != "phase1-complete" or progress.get("phase1", {}).get("confirmedAnchors") != 50:
        raise RuntimeError("geospatial phase-one ledger is not in the expected 50-anchor state")
    progress["generatedAt"] = generated_at
    progress["stageGates"]["finalOriginalUltraHdBase"] = {
        "status": "in_progress" if blocking_items else "complete",
        "candidateAuditStatus": status,
        "candidatePath": relative_path,
        "candidateSha256": sha256,
        "candidateDimensions": {"width": image["width"], "height": image["height"]},
        "auditPath": "data/geospatial/geospatial-final-base-candidate-audit.json",
        "blockingItems": blocking_items,
    }
    calibration = progress["stageGates"]["coordinateAndOverlayCalibration"]
    calibration["pixelTransformStatus"] = (
        "blocked_pending_final_base_approval_crop_and_origin"
        if blocking_items
        else "ready_for_control_pixel_measurement"
    )
    write_json(PROGRESS, progress)

    print(json.dumps({
        "status": status,
        "path": relative_path,
        "sha256": sha256,
        "dimensions": {"width": image["width"], "height": image["height"]},
        "blockingItems": blocking_items,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

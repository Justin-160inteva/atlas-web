#!/usr/bin/env python3
"""Run bounded recovery with telemetry preservation and v12 normalization."""
from __future__ import annotations

import json
import pathlib

import run_scan_with_auto_recovery as base
from publish_runtime_progress_v2 import emit

base.emit_runtime_progress = emit
_original_run = base.run


def run(command: list[str], timeout: int):
    result = _original_run(command, timeout)
    if any(part.endswith("diagnose_and_recover_scan_v2.py") for part in command):
        manifest_arg = command[-1]
        path = (base.ROOT / manifest_arg).resolve()
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if str(manifest.get("analyzer", "")).endswith("analyze_authorized_video_v11.py"):
                manifest["analyzer"] = "tools/analyze_authorized_video_v12.py"
                manifest.setdefault("compatibilityFixes", {})["preserveDownloadTelemetryAcrossStages"] = True
                temporary = pathlib.Path(str(path) + ".tmp")
                temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(path)
        except Exception:
            pass
    return result


base.run = run

if __name__ == "__main__":
    raise SystemExit(base.main())

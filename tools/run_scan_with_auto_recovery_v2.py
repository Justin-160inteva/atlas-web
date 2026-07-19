#!/usr/bin/env python3
"""Run the bounded recovery orchestrator with telemetry-preserving progress output."""
from __future__ import annotations

import run_scan_with_auto_recovery as base
from publish_runtime_progress_v2 import emit

base.emit_runtime_progress = emit

if __name__ == "__main__":
    raise SystemExit(base.main())

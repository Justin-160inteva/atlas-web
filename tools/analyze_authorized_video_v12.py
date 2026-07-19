#!/usr/bin/env python3
"""Atlas v12 analyzer: v11 transfer engine plus telemetry-preserving publisher."""
from __future__ import annotations

import analyze_authorized_video_v11 as v11
from publish_runtime_progress_v2 import emit

# All stages in the imported analyzer chain use the same telemetry-preserving publisher.
v11.v9.emit_runtime_progress = emit
v11.v9.v6.emit_runtime_progress = emit
v11.runner.base.emit_runtime_progress = emit

if __name__ == "__main__":
    raise SystemExit(v11.v9.v6.main())

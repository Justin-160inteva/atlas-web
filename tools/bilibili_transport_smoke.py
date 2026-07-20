#!/usr/bin/env python3
"""Fast deterministic 96-check gate for the Atlas v13 source transport."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import urllib.parse

import bilibili_transport_v13 as transport


def main() -> int:
    checks: list[str] = []

    def check(name: str, condition: object) -> None:
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def raises(name: str, function: object) -> None:
        try:
            function()  # type: ignore[operator]
        except (TypeError, ValueError):
            checks.append(name)
            return
        raise AssertionError(name)

    # 16 WBI key/signature checks.
    img = "0123456789abcdef0123456789abcdef"
    sub = "fedcba9876543210fedcba9876543210"
    nav = {
        "wbi_img": {
            "img_url": f"https://i.example/{img}.png",
            "sub_url": f"https://i.example/{sub}.png",
        }
    }
    key = transport.extract_mixin_key(nav)
    check("wbi-key-known-vector", key == "1022a87ffdaf532cb45ee953dce8c96d")
    check("wbi-key-nested-data", transport.extract_mixin_key({"data": nav}) == key)
    raises("wbi-key-rejects-incomplete-nav", lambda: transport.extract_mixin_key({"wbi_img": {}}))
    original = {"bvid": "BV1test", "cid": 42, "unsafe": "a!b'c(d)e*f"}
    signed = transport.sign_wbi_params(original, key, timestamp=1_700_000_000)
    check("wbi-sign-does-not-mutate", "wts" not in original and "w_rid" not in original)
    check("wbi-sign-filters-reserved-characters", signed["unsafe"] == "abcdef")
    for offset in range(11):
        timestamp = 1_700_000_001 + offset
        value = transport.sign_wbi_params(original, key, timestamp=timestamp)
        unsigned = {name: item for name, item in value.items() if name != "w_rid"}
        query = urllib.parse.urlencode({name: unsigned[name] for name in sorted(unsigned)})
        expected = hashlib.md5(f"{query}{key}".encode()).hexdigest()
        check(f"wbi-signature-vector-{offset:02d}", value["w_rid"] == expected and value["wts"] == str(timestamp))

    # 16 CDN candidate ordering and filtering checks.
    for index in range(12):
        primary = f"https://primary-{index}.example/video.m4s"
        backup = f"https://backup-{index}.example/video.m4s"
        values = transport.stream_candidates({"baseUrl": primary, "backupUrl": [backup, primary]})
        check(f"cdn-backup-first-{index:02d}", values == [backup, primary])
    check(
        "cdn-primary-first-option",
        transport.stream_candidates(
            {"base_url": "https://p.example/v", "backup_url": ["https://b.example/v"]},
            prefer_backups=False,
        ) == ["https://p.example/v", "https://b.example/v"],
    )
    check(
        "cdn-rejects-unsafe-schemes",
        transport.stream_candidates({"url": "file:///tmp/video", "backup_url": "javascript:alert(1)"}) == [],
    )
    check(
        "cdn-deduplicates-alternate-keys",
        transport.stream_candidates({"url": "https://p.example/v", "baseUrl": "https://p.example/v"}) == ["https://p.example/v"],
    )
    check(
        "cdn-accepts-camel-and-snake-backups",
        transport.stream_candidates({
            "baseUrl": "https://p.example/v",
            "backupUrl": "https://b1.example/v",
            "backup_url": ["https://b2.example/v"],
        }) == ["https://b1.example/v", "https://b2.example/v", "https://p.example/v"],
    )

    # 16 codec/height selection checks.
    for index in range(12):
        ceiling = 240 + index * 15
        payload = {
            "dash": {"video": [
                {"height": ceiling, "codecs": "avc1.64001f", "bandwidth": 100 + index, "baseUrl": f"https://avc{index}.example/v"},
                {"height": ceiling, "codecs": "av01.0.04M.08", "bandwidth": 300 + index, "baseUrl": f"https://av1{index}.example/v"},
                {"height": ceiling + 360, "codecs": "avc1.640028", "bandwidth": 500 + index, "baseUrl": f"https://hd{index}.example/v"},
            ]}
        }
        selected = transport.select_dash_video(payload, max_height=ceiling)
        check(f"dash-prefers-compatible-avc-{index:02d}", selected and selected["baseUrl"].startswith("https://avc"))

    class FakeHeartbeat:
        def __init__(self) -> None:
            self.updates: list[dict[str, object]] = []

        def update(self, **values: object) -> None:
            self.updates.append(values)

    fake_runner = types.SimpleNamespace()
    fake_v9 = types.SimpleNamespace(v6=types.SimpleNamespace(main=lambda: 0), emit_runtime_progress=lambda *_a, **_k: None)
    fake_v11 = types.SimpleNamespace(
        v9=fake_v9,
        runner=fake_runner,
        MIB=1024 * 1024,
        _settings=lambda: {},
        _job=lambda: {},
        _parallel_range_download=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("unexpected parallel path")),
    )
    fake_v12 = types.ModuleType("analyze_authorized_video_v12")
    fake_v12.v11 = fake_v11
    previous_v12 = sys.modules.get("analyze_authorized_video_v12")
    sys.modules["analyze_authorized_video_v12"] = fake_v12
    try:
        spec = importlib.util.spec_from_file_location(
            "atlas_analyzer_v13_smoke",
            pathlib.Path(__file__).with_name("analyze_authorized_video_v13.py"),
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load v13 analyzer")
        analyzer_v13 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analyzer_v13)
    finally:
        if previous_v12 is None:
            sys.modules.pop("analyze_authorized_video_v12", None)
        else:
            sys.modules["analyze_authorized_video_v12"] = previous_v12

    resume_calls: list[tuple[str, int]] = []

    def fake_probe(_candidate: str, declared: int) -> tuple[bool, int]:
        return False, declared

    def fake_resume(candidate: str, target: pathlib.Path, **_values: object) -> None:
        resume_calls.append((candidate, target.stat().st_size if target.exists() else 0))
        if "first" in candidate:
            target.write_bytes(b"a" * 1024)
            raise RuntimeError("HTTP 503 https://first.example/video?token=secret")
        with target.open("ab") as handle:
            handle.write(b"b" * 1024)

    fake_v11._range_probe = fake_probe
    fake_v11._single_stream_resume = fake_resume
    with tempfile.TemporaryDirectory(prefix="atlas-v13-smoke-") as directory:
        target = pathlib.Path(directory) / "stream.m4s"
        size, diagnostics = analyzer_v13._download_stream(
            {
                "declaredSize": 2048,
                "candidates": ["https://first.example/video", "https://second.example/video"],
            },
            target,
            heartbeat=FakeHeartbeat(),
            downloaded_before=0,
            segment_index=1,
            settings={"rangeRetriesPerCdn": 1},
        )
        check("runtime-cdn-resume-size", size == 2048)
        check("runtime-cdn-resume-content", target.read_bytes() == b"a" * 1024 + b"b" * 1024)
        check("runtime-cdn-resume-offset", resume_calls == [("https://first.example/video", 0), ("https://second.example/video", 1024)])
        check("runtime-cdn-diagnostic-privacy", diagnostics and "first.example" not in diagnostics[0] and "HTTP 503" in diagnostics[0])

    # 16 media-plan checks.
    for index in range(12):
        plan = transport.build_media_plan({
            "durl": [{
                "url": f"https://p{index}.example/v.flv",
                "backup_url": [f"https://b{index}.example/v.flv"],
                "size": 1024 + index,
            }]
        })
        check(
            f"progressive-plan-{index:02d}",
            plan["kind"] == "legacy-progressive"
            and plan["streams"][0]["declaredSize"] == 1024 + index
            and plan["streams"][0]["candidates"][0].startswith("https://b"),
        )
    dash_and_durl = {
        "dash": {"video": [{"height": 360, "codecs": "avc1", "base_url": "https://dash.example/v"}]},
        "durl": [{"url": "https://legacy.example/v"}],
    }
    check("media-plan-prefers-dash", transport.build_media_plan(dash_and_durl)["kind"] == "wbi-dash-video")
    check("media-plan-records-video-only-extension", transport.build_media_plan(dash_and_durl)["streams"][0]["extension"] == "m4s")
    check("media-plan-can-prefer-primary", transport.build_media_plan({
        "durl": [{"url": "https://p.example/v", "backup_url": ["https://b.example/v"]}],
    }, prefer_backups=False)["streams"][0]["candidates"][0] == "https://p.example/v")
    raises("media-plan-rejects-empty-response", lambda: transport.build_media_plan({}))

    # 16 verified source-identity checks.
    for page in range(25, 36):
        job = {"batch": {"page": page, "cid": 9000 + page, "sourceKey": f"BV1Atlas:p{page}"}}
        identity = transport.validate_job_identity(job, f"https://www.bilibili.com/video/BV1Atlas?p={page}")
        check(f"identity-page-{page}", identity == ("BV1Atlas", page, 9000 + page))
    raises(
        "identity-rejects-bvid-mismatch",
        lambda: transport.validate_job_identity(
            {"batch": {"page": 33, "cid": 33, "sourceKey": "BV1Expected:p33"}},
            "https://www.bilibili.com/video/BV1Other?p=33",
        ),
    )
    raises(
        "identity-rejects-page-mismatch",
        lambda: transport.validate_job_identity(
            {"batch": {"page": 33, "cid": 33, "sourceKey": "BV1Atlas:p33"}},
            "https://www.bilibili.com/video/BV1Atlas?p=34",
        ),
    )
    raises(
        "identity-requires-catalog-cid",
        lambda: transport.validate_job_identity(
            {"batch": {"page": 33, "sourceKey": "BV1Atlas:p33"}},
            "https://www.bilibili.com/video/BV1Atlas?p=33",
        ),
    )
    raises("identity-requires-bvid", lambda: transport.validate_job_identity({"batch": {"cid": 1}}, "https://example.com"))
    check(
        "identity-infers-page-without-query",
        transport.validate_job_identity(
            {"batch": {"page": 33, "cid": 33, "sourceKey": "BV1Atlas:p33"}},
            "https://www.bilibili.com/video/BV1Atlas",
        ) == ("BV1Atlas", 33, 33),
    )

    # 16 fingerprint and diagnostic-privacy checks.
    for seed in range(12):
        fingerprint = transport.fingerprint_params(seed)
        interaction = json.loads(fingerprint["dm_img_inter"])
        check(
            f"fingerprint-shape-{seed:02d}",
            fingerprint["dm_img_list"] == "[]"
            and "=" not in fingerprint["dm_img_str"]
            and len(interaction["wh"]) == len(interaction["of"]) == 3
            and interaction["ds"] == [],
        )
    check(
        "diagnostic-redacts-url",
        "example.com" not in transport.redact_diagnostic("HTTP 503 https://cdn.example.com/video?token=secret"),
    )
    check(
        "diagnostic-redacts-cookie",
        "secret" not in transport.redact_diagnostic("cookie=secret HTTP 412"),
    )
    check(
        "diagnostic-redacts-temporary-path",
        "/tmp/" not in transport.redact_diagnostic("failed /tmp/atlas-authorized-123/source.m4s"),
    )
    check(
        "diagnostic-preserves-status-class",
        "HTTP 503" in transport.redact_diagnostic("HTTP 503 https://cdn.example/v"),
    )

    if len(checks) != 96:
        raise AssertionError(f"expected 96 checks, executed {len(checks)}")
    print("96/96 v13 WBI metadata, CDN rotation, identity, and privacy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

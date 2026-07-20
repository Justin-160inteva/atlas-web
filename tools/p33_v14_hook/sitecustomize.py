#!/usr/bin/env python3
"""Conditional transport hardening for the one-time P33 v14 retry.

Python imports ``sitecustomize`` automatically when this directory is placed on
``PYTHONPATH``.  The hook is inert unless ``ATLAS_FORCE_HTTP11=1`` is present.
It changes only curl_cffi's module-level request helpers, so existing bounded
range/resume, authorization, privacy, and media-retention rules stay unchanged.
"""
from __future__ import annotations

import os
from typing import Any

ATLAS_HTTP11_PATCHED = False


def _install() -> bool:
    if os.environ.get("ATLAS_FORCE_HTTP11") != "1":
        return False

    from curl_cffi import CurlHttpVersion, requests

    if getattr(requests, "_atlas_http11_patched", False):
        return True

    original_request = requests.request
    original_get = requests.get

    def request(method: str, url: str, **kwargs: Any):
        kwargs.setdefault("http_version", CurlHttpVersion.V1_1)
        return original_request(method, url, **kwargs)

    def get(url: str, **kwargs: Any):
        kwargs.setdefault("http_version", CurlHttpVersion.V1_1)
        return original_get(url, **kwargs)

    requests.request = request
    requests.get = get
    requests._atlas_http11_patched = True
    requests._atlas_http11_original_request = original_request
    requests._atlas_http11_original_get = original_get
    return True


ATLAS_HTTP11_PATCHED = _install()

#!/usr/bin/env python3
"""Audit 达达猪 authorized-video matches before map anchoring."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / 'data/batch-analysis/dada-author-catalog-status.json'
REPORT_PATH = ROOT / 'data/batch-analysis/dada-catalog-quality-audit.json'
QUEUE_PATH = ROOT / 'data/analysis-jobs/dada-quality-reprocess.json'
SEQ_RE = re.compile(r'(?:攻略[】〗\s]*)?(\d{1,2})(?:\s|[^0-9])')
BVID_RE = re.compile(r'BV[0-9A-Za-z]+')


def sequence_from_title(title: str) -> int | None:
    match = SEQ_RE.search(str(title or ''))
    return int(match.group(1)) if match else None


def keyword_set(title: str) -> set[str]:
    text = re.sub(r'[【】〖〗（）()·:：\-_0-9]', ' ', str(title or '').lower())
    stop = {'刺客信条影', '新手攻略', '攻略', '全收集', '解锁技能', '位置', '个'}
    return {token for token in re.split(r'\s+', text) if len(token) > 1 and token not in stop}


def bvid_of(item: dict) -> str | None:
    values = [item.get('url'), item.get('lastAttempt', {}).get('resolution', {}).get('url'), item.get('lastAttempt', {}).get('resolution', {}).get('bvid')]
    for value in values:
        match = BVID_RE.search(str(value or ''))
        if match:
            return match.group(0)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--fail-on-critical', action='store_true')
    args = parser.parse_args()

    status = json.loads(STATUS_PATH.read_text(encoding='utf-8'))
    items = status.get('items', [])
    findings: list[dict] = []
    reprocess: set[int] = set()

    def add(severity: str, code: str, sequence: int | None, message: str, **evidence) -> None:
        findings.append({'severity': severity, 'code': code, 'sequence': sequence, 'message': message, 'evidence': evidence})
        if severity == 'critical' and sequence is not None:
            reprocess.add(sequence)

    by_bvid: dict[str, list[int]] = defaultdict(list)
    by_url: dict[str, list[int]] = defaultdict(list)
    for item in items:
        seq = int(item.get('sequence') or 0)
        bvid = bvid_of(item)
        if bvid:
            by_bvid[bvid].append(seq)
        url = str(item.get('url') or '')
        if url:
            by_url[url].append(seq)

        expected_title = str(item.get('title') or '')
        resolution = item.get('lastAttempt', {}).get('resolution', {})
        resolved_title = str(resolution.get('title') or expected_title)
        expected_seq = seq or sequence_from_title(expected_title)
        resolved_seq = sequence_from_title(resolved_title)
        if resolved_seq is not None and expected_seq and resolved_seq != expected_seq:
            add('critical', 'SEQUENCE_MISMATCH', seq, f'Expected video {expected_seq:02d}, resolved title indicates {resolved_seq:02d}', expectedTitle=expected_title, resolvedTitle=resolved_title, bvid=bvid)

        expected_keywords = keyword_set(expected_title)
        resolved_keywords = keyword_set(resolved_title)
        if expected_keywords and resolved_keywords:
            overlap = len(expected_keywords & resolved_keywords) / max(1, len(expected_keywords | resolved_keywords))
            if overlap < 0.25:
                add('critical', 'TITLE_TOPIC_MISMATCH', seq, 'Resolved title topic differs from catalog title', expectedTitle=expected_title, resolvedTitle=resolved_title, overlap=round(overlap, 3), bvid=bvid)
            elif overlap < 0.5:
                add('warning', 'TITLE_TOPIC_LOW_CONFIDENCE', seq, 'Resolved title has low keyword overlap', expectedTitle=expected_title, resolvedTitle=resolved_title, overlap=round(overlap, 3), bvid=bvid)

        author = str(resolution.get('author') or status.get('author') or '')
        if author and author != status.get('author'):
            add('critical', 'AUTHOR_MISMATCH', seq, f'Resolved author is {author}', expected=status.get('author'), bvid=bvid)

        score = resolution.get('score')
        if isinstance(score, (int, float)) and score < 220:
            add('warning', 'LOW_MATCH_SCORE', seq, f'Match score is only {score}', score=score, bvid=bvid)

        result_path = str(item.get('resultPath') or '')
        if not result_path or not (ROOT / result_path).exists():
            add('critical', 'RESULT_MISSING', seq, 'Imported entry has no analysis result file', resultPath=result_path, bvid=bvid)

        if item.get('state') != 'imported':
            add('critical', 'NOT_IMPORTED', seq, f"Entry state is {item.get('state')}", bvid=bvid)

    for bvid, sequences in sorted(by_bvid.items()):
        unique = sorted(set(sequences))
        if len(unique) > 1:
            for seq in unique:
                add('critical', 'DUPLICATE_BVID', seq, f'BVID {bvid} is assigned to multiple catalog entries {unique}', bvid=bvid, sequences=unique)

    for url, sequences in sorted(by_url.items()):
        unique = sorted(set(sequences))
        if len(unique) > 1:
            for seq in unique:
                add('critical', 'DUPLICATE_URL', seq, f'URL is assigned to multiple catalog entries {unique}', url=url, sequences=unique)

    critical = sum(item['severity'] == 'critical' for item in findings)
    warnings = sum(item['severity'] == 'warning' for item in findings)
    report = {
        'schemaVersion': 1,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'batchId': status.get('batchId'),
        'author': status.get('author'),
        'pipelineComplete': bool(status.get('complete')),
        'qualityComplete': critical == 0 and len(items) == status.get('summary', {}).get('total', len(items)),
        'summary': {
            'catalogItems': len(items),
            'critical': critical,
            'warnings': warnings,
            'reprocessCount': len(reprocess),
            'reprocessSequences': sorted(reprocess)
        },
        'findings': findings
    }
    queue = {
        'schemaVersion': 1,
        'generatedAt': report['generatedAt'],
        'author': status.get('author'),
        'authorizationId': status.get('authorizationId'),
        'reason': 'catalog-quality-audit',
        'sequences': sorted(reprocess),
        'items': [
            {
                'sequence': int(item.get('sequence') or 0),
                'externalSourceId': item.get('externalSourceId'),
                'expectedTitle': item.get('title'),
                'currentUrl': item.get('url'),
                'currentBvid': bvid_of(item),
                'resultPath': item.get('resultPath')
            }
            for item in items if int(item.get('sequence') or 0) in reprocess
        ]
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))
    if args.fail_on_critical and critical:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

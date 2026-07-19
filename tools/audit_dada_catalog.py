#!/usr/bin/env python3
"""Audit 达达猪 authorized-video matches before any reprocessing.

Phase 2 separates three very different states:

1. canonical entries that correctly own a duplicated BVID and must be retained;
2. entries whose URL/BVID must be resolved before they can be reprocessed;
3. catalog identities whose expected title is itself inconsistent with the sequence.

The audit never downloads media. It only writes a quality report and a safe
resolution queue. A later phase may consume that queue after exact URLs are
verified.
"""
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
    text = re.sub(r'[【】〖〗（）()·:：\-_0-9%]', ' ', str(title or '').lower())
    stop = {'刺客信条影', '刺客信条', '新手攻略', '攻略', '全收集', '解锁技能', '位置', '个'}
    return {token for token in re.split(r'\s+', text) if len(token) > 1 and token not in stop}


def topic_overlap(expected: str, resolved: str) -> float:
    left = keyword_set(expected)
    right = keyword_set(resolved)
    if not left or not right:
        return 1.0 if expected.strip() == resolved.strip() else 0.0
    return len(left & right) / max(1, len(left | right))


def bvid_of(item: dict) -> str | None:
    resolution = item.get('lastAttempt', {}).get('resolution', {})
    values = [item.get('url'), resolution.get('url'), resolution.get('bvid')]
    for value in values:
        match = BVID_RE.search(str(value or ''))
        if match:
            return match.group(0)
    return None


def resolved_title_of(item: dict) -> str:
    resolution = item.get('lastAttempt', {}).get('resolution', {})
    return str(resolution.get('title') or item.get('title') or '')


def resolution_score_of(item: dict) -> float | None:
    value = item.get('lastAttempt', {}).get('resolution', {}).get('score')
    return float(value) if isinstance(value, (int, float)) else None


def is_strong_canonical(item: dict) -> bool:
    sequence = int(item.get('sequence') or 0)
    expected = str(item.get('title') or '')
    resolved = resolved_title_of(item)
    resolved_sequence = sequence_from_title(resolved)
    return (
        sequence > 0
        and resolved_sequence == sequence
        and topic_overlap(expected, resolved) >= 0.5
        and sequence_from_title(expected) in {None, sequence}
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--fail-on-critical', action='store_true')
    args = parser.parse_args()

    status = json.loads(STATUS_PATH.read_text(encoding='utf-8'))
    items = status.get('items', [])
    item_by_sequence = {int(item.get('sequence') or 0): item for item in items}
    findings: list[dict] = []
    resolution_required: set[int] = set()
    identity_required: set[int] = set()
    canonical_retained: set[int] = set()

    def add(severity: str, code: str, sequence: int | None, message: str, **evidence) -> None:
        findings.append({
            'severity': severity,
            'code': code,
            'sequence': sequence,
            'message': message,
            'evidence': evidence,
        })

    by_bvid: dict[str, list[int]] = defaultdict(list)
    by_url: dict[str, list[int]] = defaultdict(list)

    for item in items:
        sequence = int(item.get('sequence') or 0)
        expected_title = str(item.get('title') or '')
        resolved_title = resolved_title_of(item)
        expected_title_sequence = sequence_from_title(expected_title)
        resolved_sequence = sequence_from_title(resolved_title)
        bvid = bvid_of(item)
        overlap = topic_overlap(expected_title, resolved_title)

        if bvid:
            by_bvid[bvid].append(sequence)
        url = str(item.get('url') or '')
        if url:
            by_url[url].append(sequence)

        if expected_title_sequence is not None and expected_title_sequence != sequence:
            identity_required.add(sequence)
            add(
                'critical',
                'CATALOG_IDENTITY_MISMATCH',
                sequence,
                f'Catalog sequence is {sequence:02d}, but its expected title indicates {expected_title_sequence:02d}',
                expectedTitle=expected_title,
                titleSequence=expected_title_sequence,
                bvid=bvid,
            )

        if resolved_sequence is not None and resolved_sequence != sequence:
            resolution_required.add(sequence)
            add(
                'critical',
                'SEQUENCE_MISMATCH',
                sequence,
                f'Expected video {sequence:02d}, resolved title indicates {resolved_sequence:02d}',
                expectedTitle=expected_title,
                resolvedTitle=resolved_title,
                bvid=bvid,
            )

        if expected_title and resolved_title and overlap < 0.25:
            resolution_required.add(sequence)
            add(
                'critical',
                'TITLE_TOPIC_MISMATCH',
                sequence,
                'Resolved title topic differs from catalog title',
                expectedTitle=expected_title,
                resolvedTitle=resolved_title,
                overlap=round(overlap, 3),
                bvid=bvid,
            )
        elif expected_title and resolved_title and overlap < 0.5:
            add(
                'warning',
                'TITLE_TOPIC_LOW_CONFIDENCE',
                sequence,
                'Resolved title has low keyword overlap',
                expectedTitle=expected_title,
                resolvedTitle=resolved_title,
                overlap=round(overlap, 3),
                bvid=bvid,
            )

        author = str(item.get('lastAttempt', {}).get('resolution', {}).get('author') or status.get('author') or '')
        if author and author != status.get('author'):
            resolution_required.add(sequence)
            add('critical', 'AUTHOR_MISMATCH', sequence, f'Resolved author is {author}', expected=status.get('author'), bvid=bvid)

        score = resolution_score_of(item)
        if score is not None and score < 220:
            add('warning', 'LOW_MATCH_SCORE', sequence, f'Match score is only {score}', score=score, bvid=bvid)

        result_path = str(item.get('resultPath') or '')
        if not result_path or not (ROOT / result_path).exists():
            resolution_required.add(sequence)
            add('critical', 'RESULT_MISSING', sequence, 'Imported entry has no analysis result file', resultPath=result_path, bvid=bvid)

        if item.get('state') != 'imported':
            resolution_required.add(sequence)
            add('critical', 'NOT_IMPORTED', sequence, f"Entry state is {item.get('state')}", bvid=bvid)

    duplicate_groups: list[dict] = []
    processed_groups: set[tuple[int, ...]] = set()

    def classify_duplicate(kind: str, value: str, sequences: list[int]) -> None:
        unique = sorted(set(sequences))
        key = tuple(unique)
        if len(unique) < 2 or key in processed_groups:
            return
        processed_groups.add(key)

        strong = [sequence for sequence in unique if is_strong_canonical(item_by_sequence[sequence])]
        canonical = strong[0] if len(strong) == 1 else None
        if canonical is not None:
            canonical_retained.add(canonical)
            suspects = [sequence for sequence in unique if sequence != canonical]
            resolution_required.update(suspects)
            add(
                'info',
                'DUPLICATE_CANONICAL_RETAINED',
                canonical,
                f'{kind} duplicate group {unique} has canonical sequence {canonical:02d}; keep it and resolve the others',
                duplicateType=kind,
                duplicateValue=value,
                sequences=unique,
                canonicalSequence=canonical,
                suspectSequences=suspects,
            )
            for sequence in suspects:
                add(
                    'critical',
                    f'DUPLICATE_{kind}_MISASSIGNED',
                    sequence,
                    f'{kind} belongs to canonical sequence {canonical:02d}, not sequence {sequence:02d}',
                    duplicateValue=value,
                    sequences=unique,
                    canonicalSequence=canonical,
                )
        else:
            resolution_required.update(unique)
            add(
                'critical',
                f'DUPLICATE_{kind}_AMBIGUOUS',
                None,
                f'{kind} duplicate group {unique} has no unique canonical owner',
                duplicateValue=value,
                sequences=unique,
                strongCandidates=strong,
            )

        duplicate_groups.append({
            'type': kind,
            'value': value,
            'sequences': unique,
            'canonicalSequence': canonical,
            'strongCandidates': strong,
        })

    for bvid, sequences in sorted(by_bvid.items()):
        classify_duplicate('BVID', bvid, sequences)
    for url, sequences in sorted(by_url.items()):
        classify_duplicate('URL', url, sequences)

    # A canonical entry is retained even though it appears in a duplicate group.
    resolution_required.difference_update(canonical_retained)
    identity_required.difference_update(canonical_retained)

    queue_sequences = sorted(resolution_required | identity_required)
    critical = sum(finding['severity'] == 'critical' for finding in findings)
    warnings = sum(finding['severity'] == 'warning' for finding in findings)

    report = {
        'schemaVersion': 2,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'batchId': status.get('batchId'),
        'author': status.get('author'),
        'pipelineComplete': bool(status.get('complete')),
        'qualityComplete': not queue_sequences and critical == 0,
        'summary': {
            'catalogItems': len(items),
            'critical': critical,
            'warnings': warnings,
            'affectedCount': len(set(queue_sequences) | canonical_retained),
            'canonicalRetainedCount': len(canonical_retained),
            'canonicalRetainedSequences': sorted(canonical_retained),
            'resolutionRequiredCount': len(resolution_required),
            'resolutionRequiredSequences': sorted(resolution_required),
            'identityRequiredCount': len(identity_required),
            'identityRequiredSequences': sorted(identity_required),
            'queueCount': len(queue_sequences),
            'queueSequences': queue_sequences,
        },
        'duplicateGroups': duplicate_groups,
        'findings': findings,
    }

    queue_items = []
    for sequence in queue_sequences:
        item = item_by_sequence[sequence]
        identity_first = sequence in identity_required
        queue_items.append({
            'sequence': sequence,
            'externalSourceId': item.get('externalSourceId'),
            'expectedTitle': item.get('title'),
            'resolvedTitle': resolved_title_of(item),
            'currentUrl': item.get('url'),
            'currentBvid': bvid_of(item),
            'resultPath': item.get('resultPath'),
            'action': 'verify_catalog_identity_then_resolve_url' if identity_first else 'resolve_exact_url_then_reprocess',
            'safeToDownloadNow': False,
            'requiresExactUrlVerification': True,
        })

    queue = {
        'schemaVersion': 2,
        'generatedAt': report['generatedAt'],
        'author': status.get('author'),
        'authorizationId': status.get('authorizationId'),
        'reason': 'catalog-quality-audit-phase2',
        'canonicalRetainedSequences': sorted(canonical_retained),
        'resolutionRequiredSequences': sorted(resolution_required),
        'identityRequiredSequences': sorted(identity_required),
        'sequences': queue_sequences,
        'automaticDownloadEnabled': False,
        'items': queue_items,
    }

    # Structural safety invariants: correct duplicate owners can never enter the
    # reprocessing queue, and no item may be downloaded before URL verification.
    if canonical_retained & set(queue_sequences):
        raise RuntimeError('canonical entries leaked into the reprocessing queue')
    if any(item['safeToDownloadNow'] for item in queue_items):
        raise RuntimeError('unverified item was marked safe to download')
    if any(not item['action'] for item in queue_items):
        raise RuntimeError('queue item is missing an action')

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))

    if args.fail_on_critical and queue_sequences:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

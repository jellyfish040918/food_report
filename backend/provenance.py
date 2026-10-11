"""Reproducible evidence receipts, not a claim of semantic fact checking."""
import hashlib
import json
from datetime import datetime, timezone


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def receipt(context, result, job_id, kind, generated):
    evidence = context['evidence']
    available = [e['id'] for e in evidence]
    if len(available) != len(set(available)):
        raise ValueError('Duplicate source identifiers')
    items = result['localization'] if kind == 'report' else result['points']
    links = []
    for index, item in enumerate(items):
        refs = item['evidenceIds']
        if not refs or len(set(refs)) != len(refs) or any(ref not in available for ref in refs):
            raise ValueError('Every item must reference distinct sources in this run')
        links.append({'item': index + 1, 'evidenceIds': refs})
    return {
        'engine': 'flavo-agent-v2', 'receiptVersion': 1, 'runId': job_id,
        'snapshotDate': context['snapshotDate'], 'evidenceAuthority': 'server',
        'validation': 'structure-and-evidence-ids', 'reviewRequired': True,
        'generatedByAI': generated,
        'checkedAt': datetime.now(timezone.utc).isoformat(),
        'evidenceDigest': digest(evidence),
        'evidenceCount': len(evidence), 'linkedItemCount': len(links),
        'citedEvidenceCount': len({ref for link in links for ref in link['evidenceIds']}),
        'links': links,
        'checks': {'structure': 'passed', 'sourceReferences': 'passed' if links else 'not_applicable',
                   'semanticAccuracy': 'human_review_required', 'freshness': 'snapshot_only'},
    }

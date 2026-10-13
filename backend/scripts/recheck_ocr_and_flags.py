# -*- coding: utf-8 -*-
"""One-off fix after the OCR/duplicate-detection changes (run backup_database.py first):

1. Re-runs OCR on documents checked by the old pipeline, so they get the new
   status and the student-facing upload warning.
2. Resolves open near-duplicate flags that are just a shared template - the
   flagged document carries its uploader's own name, not the other applicant's.

Prints counts only (no names or document text).

Usage (from backend/): python scripts/recheck_ocr_and_flags.py"""
import os
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import documents as D  # noqa: E402
from extensions import get_db, _fs  # noqa: E402
from ocr import extract_text, names_other_person  # noqa: E402


def recheck_old_ocr_results(db):
    before, after, warned = Counter(), Counter(), Counter()
    for a in db.applicants.find({}):
        for d in a.get('documents', []):
            # 'upload_warning' is written by every check since the new pipeline,
            # so its absence marks an old result.
            if (d.get('status') != 'Uploaded' or d.get('document_name') == D.SELFIE_DOC_LABEL
                    or not d.get('ocr_status') or 'upload_warning' in d):
                continue
            result = D.run_ocr_check(db, a, a['_id'], d['document_name'], a['organization_id'])
            if 'error' in result:
                after['error'] += 1
                continue
            before[d['ocr_status']] += 1
            after[result['status']] += 1
            warning = D.student_upload_warning(result, d['document_name'])
            warned[warning.split('.')[0][:45] if warning else 'no warning'] += 1
    print('Re-checked:', sum(before.values()))
    print('  before:', dict(before))
    print('  after: ', dict(after))
    print('  student warnings now shown:', dict(warned))


def resolve_template_near_duplicates(db):
    names = {a['_id']: a.get('full_name', '') for a in db.applicants.find({}, {'full_name': 1})}
    kept = resolved = 0
    for f in list(db.duplicate_flags.find({'reason': 'near_duplicate_document', 'resolved': False})):
        applicant = db.applicants.find_one({'_id': f['applicant_id']}, {'documents': 1}) or {}
        doc = next((d for d in applicant.get('documents', []) if d.get('document_name') == f['document_name']), None)
        if not doc or not doc.get('gridfs_id') or f['document_name'] == D.SELFIE_DOC_LABEL:
            kept += 1
            continue
        grid_out = _fs.get(doc['gridfs_id'])
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(grid_out.filename)[1], delete=False) as tmp:
            tmp.write(grid_out.read())
            path = tmp.name
        try:
            text = extract_text(path)
        finally:
            os.remove(path)
        if names_other_person(names.get(f.get('duplicate_of_id'), ''), names.get(f['applicant_id'], ''), text):
            kept += 1
            continue
        db.duplicate_flags.update_one({'_id': f['_id']}, {'$set': {
            'resolved': True,
            'resolved_note': "Auto-resolved: same document template, with the applicant's own name on it.",
        }})
        resolved += 1
    print(f'Near-duplicate flags resolved: {resolved} | kept open: {kept}')


if __name__ == '__main__':
    db = get_db()
    recheck_old_ocr_results(db)
    resolve_template_near_duplicates(db)

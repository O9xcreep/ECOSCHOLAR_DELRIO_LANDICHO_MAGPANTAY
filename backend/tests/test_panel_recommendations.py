import io
from datetime import datetime, timedelta

from bson import ObjectId
from PIL import Image
from PIL.PngImagePlugin import PngInfo

import app as app_module
from documents import extract_metadata_flags
from helpers import REJECTION_REASONS, notify_students_if_program_closed


def _org(db):
    return app_module.get_default_organization_id(db)


def _rejected(db, cycle_id=None, ml_status='Not Eligible', email='s@test.com'):
    return db.applicants.insert_one({
        'full_name': 'Juan Cruz', 'email': email, 'cycle_id': cycle_id, 'ml_status': ml_status,
        'application': {'status': 'Rejected', 'submitted_at': datetime.utcnow()},
    }).inserted_id


# Scholarship list
def test_directory_lists_slots_and_qualifications(client, db, auth_headers, open_cycle):
    res = client.put('/api/settings', headers=auth_headers(),
                     json={'program_qualifications': [' Resident of Liliw ', ''], 'max_accepted': 7})
    assert res.status_code == 200
    org = client.get('/api/organizations/directory').get_json()['organizations'][0]
    assert org['slots'] == 7
    assert org['qualifications'] == ['Resident of Liliw']


def test_qualifications_are_validated(client, auth_headers):
    headers = auth_headers()
    for bad in ('text', [1], ['x' * 201], ['x'] * 16):
        assert client.put('/api/settings', headers=headers,
                          json={'program_qualifications': bad}).status_code == 400


# Closed notification
def test_students_are_notified_once_when_the_program_closes(client, db, auth_headers, open_cycle):
    headers = auth_headers('student')
    assert client.get('/api/notifications', headers=headers).get_json()['unread_count'] == 0
    db.program_cycles.update_one({'_id': open_cycle}, {'$set': {'deadline': datetime.utcnow() - timedelta(days=1)}})
    for _ in range(2):
        body = client.get('/api/notifications', headers=headers).get_json()
        assert [n['type'] for n in body['notifications']] == ['program_closed']


def test_extending_the_deadline_rearms_the_notification(client, db, auth_headers, open_cycle):
    auth_headers('student')
    past = {'$set': {'deadline': datetime.utcnow() - timedelta(days=1)}}
    db.program_cycles.update_one({'_id': open_cycle}, past)
    assert notify_students_if_program_closed(db, _org(db)) == 1
    later = (datetime.utcnow() + timedelta(days=3)).isoformat()
    assert client.put('/api/program-cycles/current/deadline', headers=auth_headers(),
                      json={'deadline': later}).status_code == 200
    assert notify_students_if_program_closed(db, _org(db)) == 0
    db.program_cycles.update_one({'_id': open_cycle}, past)
    assert notify_students_if_program_closed(db, _org(db)) == 1


# Rejection reasons
def test_reasons_are_saved_and_shown_to_the_student(client, db, auth_headers, open_cycle):
    aid = _rejected(db, open_cycle, email='student@test.com')
    db.settings.update_one({'organization_id': _org(db)}, {'$set': {'results_visible_override': True}}, upsert=True)
    res = client.put(f'/api/applications/{aid}/rejection-reasons', headers=auth_headers(),
                     json={'reasons': REJECTION_REASONS[:2], 'note': 'Other'})
    assert res.status_code == 200
    headers = auth_headers('student')
    url = '/api/student/application?email=student@test.com'
    shown = client.get(url, headers=headers).get_json()['application']
    assert shown['rejection_reasons'] == REJECTION_REASONS[:2]
    assert shown['rejection_note'] == 'Other'

    db.settings.update_one({'organization_id': _org(db)}, {'$set': {'results_visible_override': False}})
    hidden = client.get(url, headers=headers).get_json()['application']
    assert hidden['rejection_reasons'] == [] and hidden['rejection_note'] is None


def test_reasons_need_a_real_rejection_and_a_listed_choice(client, db, auth_headers):
    headers = auth_headers()
    url = '/api/applications/{}/rejection-reasons'
    ok = {'reasons': REJECTION_REASONS[:1]}
    assert client.put(url.format(_rejected(db, ml_status='Eligible')), headers=headers, json=ok).status_code == 400
    aid = _rejected(db)
    for bad in ({'reasons': ['made up']}, {'reasons': []}, {'reasons': [], 'note': 'x' * 301}):
        assert client.put(url.format(aid), headers=headers, json=bad).status_code == 400
    assert client.put(url.format(aid), headers=auth_headers('student'), json=ok).status_code == 403


def test_reasons_cannot_be_set_on_another_organizations_applicant(client, db, auth_headers):
    aid = _rejected(db)
    db.applicants.update_one({'_id': aid}, {'$set': {'organization_id': ObjectId()}})
    res = client.put(f'/api/applications/{aid}/rejection-reasons', headers=auth_headers(),
                     json={'reasons': REJECTION_REASONS[:1]})
    assert res.status_code == 404


def test_reconsidering_clears_the_reasons(client, db, auth_headers):
    aid, headers = _rejected(db), auth_headers()
    client.put(f'/api/applications/{aid}/rejection-reasons', headers=headers, json={'reasons': REJECTION_REASONS[:1]})
    client.put(f'/api/applications/{aid}/status', headers=headers, json={'status': 'Newly Submitted'})
    assert 'rejection_reasons' not in db.applicants.find_one({'_id': aid})['application']


# Archive
def test_archive_lists_only_the_chosen_program(client, db, auth_headers, open_cycle):
    _rejected(db, open_cycle)
    new_cycle = app_module.do_program_reset(db, _org(db), 'a@test.com')
    _rejected(db, new_cycle, email='new@test.com')
    headers = auth_headers()
    res = client.get(f'/api/applicants?cycle={open_cycle}&page=1', headers=headers)
    assert [a['email'] for a in res.get_json()['applicants']] == ['s@test.com']
    assert client.get('/api/applicants?cycle=nope', headers=headers).status_code == 400


# Edited pictures
def _jpeg(software=None):
    exif = Image.Exif()
    if software:
        exif[0x0131] = software
    out = io.BytesIO()
    Image.effect_noise((600, 600), 80).convert('RGB').save(out, 'JPEG', exif=exif)
    return out.getvalue()


def test_editing_tools_are_found_in_jpeg_png_and_xmp():
    assert extract_metadata_flags(_jpeg('Adobe Photoshop 25'), 'a.jpg')
    assert not extract_metadata_flags(_jpeg('Samsung Camera'), 'a.jpg')
    info, out = PngInfo(), io.BytesIO()
    info.add_text('Software', 'GIMP 2.10')
    Image.new('RGB', (9, 9)).save(out, 'PNG', pnginfo=info)
    assert extract_metadata_flags(out.getvalue(), 'a.png')
    out = io.BytesIO()
    Image.new('RGB', (9, 9)).save(out, 'JPEG', xmp=b'<x xmp:CreatorTool="Canva"/>')
    assert extract_metadata_flags(out.getvalue(), 'a.jpg')


def test_upload_checks_the_original_files_metadata(client, db, auth_headers):
    headers = auth_headers('student')
    aid = db.applicants.insert_one({'full_name': 'Juan', 'email': 'student@test.com',
                                    'application': {'status': 'Newly Submitted'}, 'documents': []}).inserted_id
    res = client.post('/api/upload', headers=headers, content_type='multipart/form-data', data={
        'applicant_id': str(aid), 'document_name': 'School ID',
        'file': (io.BytesIO(_jpeg()), 'id.jpg'),  # re-encoded by the browser: clean
        'original_header': (io.BytesIO(_jpeg('Adobe Photoshop 25')[:20000]), 'header'),
    })
    assert res.status_code == 200
    assert db.applicants.find_one({'_id': aid})['documents'][0]['metadata_flags']
    assert db.duplicate_flags.find_one({'reason': 'suspicious_metadata'})

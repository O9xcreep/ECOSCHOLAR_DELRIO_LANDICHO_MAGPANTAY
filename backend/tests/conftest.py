# -*- coding: utf-8 -*-
"""
Shared pytest fixtures. app.py talks to MongoDB via pymongo.MongoClient at
import time, so we swap that for mongomock's in-memory equivalent BEFORE
app.py is ever imported - every test then runs against a fresh in-memory
database, never the real Atlas cluster, and needs no network access at all.
"""
import os
import sys

os.environ.setdefault('MONGO_URI', 'mongodb://localhost:1/ecoscholars_test')
os.environ.setdefault('MONGO_DB_NAME', 'ecoscholars_test')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('FLASK_DEBUG', 'true')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:5173')

import mongomock
import pymongo
pymongo.MongoClient = mongomock.MongoClient  # must happen before app.py imports MongoClient

import gridfs
from bson import ObjectId


class _FakeGridFS:
    """gridfs.GridFS strictly type-checks for a real pymongo Database, which
    mongomock's Database isn't. None of this test suite exercises file
    upload/download (that needs a running Tesseract binary regardless), so a
    minimal stand-in that never touches real storage is enough here."""
    def __init__(self, *a, **kw):
        pass

    def put(self, *a, **kw):
        return ObjectId()

    def get(self, *a, **kw):
        raise gridfs.errors.NoFile("no file in fake GridFS")

    def delete(self, *a, **kw):
        pass


gridfs.GridFS = _FakeGridFS

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as app_module

from werkzeug.security import generate_password_hash


# Multi-tenancy Phase C scopes almost every applicants query by organization_id
# (see app.py). Most of this suite predates that and inserts applicant test
# fixtures directly via db.applicants.insert_one(...)/insert_many(...) with no
# organization_id at all, which those scoped queries then simply don't match.
# Rather than editing every one of those call sites across the whole suite,
# auto-tag with the default org at insert time here - mongomock keeps the same
# Collection object across drop_collection() calls (verified: dropping clears
# data, not object identity), so patching once at import time is durable for
# the whole run. A test that deliberately wants an UNTAGGED applicant (a
# legacy-data edge case) can still pass organization_id explicitly, since
# setdefault only fills it in when absent.
def _auto_tag_organization_id(collection):
    original_insert_one = collection.insert_one
    original_insert_many = collection.insert_many

    def insert_one(document, *args, **kwargs):
        document.setdefault('organization_id', app_module.get_default_organization_id(app_module._mongo_db))
        return original_insert_one(document, *args, **kwargs)

    def insert_many(documents, *args, **kwargs):
        org_id = app_module.get_default_organization_id(app_module._mongo_db)
        for doc in documents:
            doc.setdefault('organization_id', org_id)
        return original_insert_many(documents, *args, **kwargs)

    collection.insert_one = insert_one
    collection.insert_many = insert_many


_auto_tag_organization_id(app_module._mongo_db.applicants)
_auto_tag_organization_id(app_module._mongo_db.document_requirements)


@pytest.fixture(autouse=True)
def block_real_http_calls(monkeypatch):
    """This suite is documented (see the module docstring above) as never
    needing network access - mongomock covers the database side, but nothing
    stopped a test from making a REAL outbound HTTP call using whatever real
    credentials happen to be sitting in .env (app.py's load_dotenv() loads it
    unconditionally, even under pytest). That's exactly what happened once: a
    test that meant to exercise the "provider not configured" skip path
    forgot to also pin EMAIL_PROVIDER, fell through to a real, fully-configured
    Mailjet account, and sent one real email, burning real quota right after
    being asked not to.

    Blocking requests.post/get by default turns any future version of that
    mistake into an immediate, loud test failure instead of a silent real API
    call. A test that needs to exercise a real HTTP call path still can -
    unittest.mock.patch(.object) fully overrides this for its own scope and
    restores back to this blocker afterward, same as it would restore the
    real function."""
    def _blocked(*args, **kwargs):
        raise RuntimeError(
            "A real outbound HTTP call was attempted during a test (requests."
            "post/get). This suite must never make real network calls - mock "
            "it explicitly with unittest.mock.patch.object(app_module.requests, "
            "'post', ...)."
        )
    monkeypatch.setattr(app_module.requests, 'post', _blocked)
    monkeypatch.setattr(app_module.requests, 'get', _blocked)


@pytest.fixture(autouse=True)
def clean_db():
    """Every test gets a blank database - drop all collections before, not
    after, so a failed test's leftover data never leaks into the next one.
    Also resets Flask-Limiter's counters, since its storage is shared across
    the whole process: without this, a test late in the run can get a real
    429 from earlier tests' requests to the same rate-limited endpoint."""
    for name in app_module._mongo_db.list_collection_names():
        app_module._mongo_db.drop_collection(name)
    app_module.limiter.reset()
    yield


@pytest.fixture
def db():
    return app_module._mongo_db


@pytest.fixture
def open_cycle(db):
    """POST /api/apply now requires the org to have an explicitly open scholarship
    program (see is_cycle_open() in app.py). Opt-in (not autouse) since plenty of
    tests deliberately exercise the "no program set up yet" implicit-Cycle-0 state -
    only a test that itself calls /api/apply needs this. Returns the new cycle's id
    so the test can tag any applicant fixtures it inserts directly with a matching
    cycle_id (the duplicate-check queries below are scoped by cycle)."""
    org_id = app_module.get_default_organization_id(db)
    return app_module.do_program_reset(db, org_id, 'test-setup@test.com')


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    # Rate limits are real production behavior worth having, but the test suite
    # legitimately calls endpoints like /api/login far more than 8x/minute
    # across different tests sharing one process - that's a test-runner
    # artifact, not something under test here.
    app_module.app.config['RATELIMIT_ENABLED'] = False
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def make_user(db):
    """Inserts a user directly (bypassing /api/register) and returns its
    email/password/id, for tests that need a pre-existing account. `permissions`
    only matters for role='lgu_member' - pass e.g. {'can_manage_members': True}
    to grant specific scoped access; omitted keys default to False.

    Tagged with the auto-created default organization by default (matching
    every real account post multi-tenancy Phase A) - pass organization_id
    explicitly to put a user in a *different* org for cross-tenant isolation
    tests, or organization_id=False for the rare case of a legacy account
    that predates any org tagging at all."""
    def _make(email='user@test.com', password='TestPass123', role='student', full_name='Test User',
              permissions=None, organization_id=...):
        doc = {
            'full_name': full_name,
            'email': email,
            'password': generate_password_hash(password),
            'role': role,
            'status': 'active',
            'privacy_consent': True,
        }
        if role == 'lgu_member':
            doc['permissions'] = {
                'can_review_applicants': bool((permissions or {}).get('can_review_applicants')),
                'can_manage_members': bool((permissions or {}).get('can_manage_members')),
                'can_reset_program': bool((permissions or {}).get('can_reset_program')),
            }
        if organization_id is False:
            pass  # deliberately untagged, for legacy-account edge cases
        elif organization_id is not ...:
            doc['organization_id'] = organization_id
        else:
            doc['organization_id'] = app_module.get_default_organization_id(db)
        user_id = db.users.insert_one(doc).inserted_id
        return {'id': user_id, 'email': email, 'password': password, 'role': role,
                'organization_id': doc.get('organization_id')}
    return _make


@pytest.fixture
def auth_headers(client, make_user):
    """Registers+logs in a fresh account and returns the Authorization header
    for it, for tests that just need *some* authenticated user of a given role.
    For role='lgu_member', pass `permissions` to control what it can access."""
    def _headers(role='admin', permissions=None):
        user = make_user(email=f'{role}@test.com', password='TestPass123', role=role, permissions=permissions)
        res = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = res.get_json()['token']
        return {'Authorization': f'Bearer {token}'}
    return _headers

# -*- coding: utf-8 -*-
"""
Shared pytest fixtures. app.py connects to MongoDB via pymongo.MongoClient at
import time, so mongomock's in-memory equivalent is swapped in before app.py
is imported, keeping every test off the real database and network.
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
    mongomock's isn't. Minimal stand-in since this suite never exercises
    file upload/download."""
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


# Most queries are scoped by organization_id (see app.py), but most of this
# suite inserts applicant fixtures directly with no organization_id set.
# Auto-tag with the default org at insert time instead of editing every call
# site; a test that wants an untagged applicant can still pass organization_id
# explicitly, since setdefault only fills it in when absent.
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
    """Blocks real outbound HTTP calls during tests, since app.py's
    load_dotenv() loads real credentials from .env even under pytest and a
    misconfigured test could otherwise hit a real API. A test that needs a
    real HTTP call path can still patch requests.post/get for its own scope."""
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
    """Drops all collections before each test (not after) so a failed test's
    leftover data can't leak into the next one, and resets Flask-Limiter's
    counters since its storage is shared across the whole process."""
    for name in app_module._mongo_db.list_collection_names():
        app_module._mongo_db.drop_collection(name)
    app_module.limiter.reset()
    yield


@pytest.fixture
def db():
    return app_module._mongo_db


@pytest.fixture
def open_cycle(db):
    """Opens a scholarship program cycle, required by POST /api/apply (see
    is_cycle_open()). Opt-in since many tests deliberately exercise the
    no-program state. Returns the cycle id for tagging applicant fixtures."""
    org_id = app_module.get_default_organization_id(db)
    return app_module.do_program_reset(db, org_id, 'test-setup@test.com')


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    # Disabled: tests share one process and legitimately exceed per-minute
    # limits on endpoints like /api/login across different test cases.
    app_module.app.config['RATELIMIT_ENABLED'] = False
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def make_user(db):
    """Inserts a user directly (bypassing /api/register), for tests needing a
    pre-existing account. `permissions` applies only to role='lgu_member'.
    Tagged with the default organization unless organization_id is passed
    explicitly, or False for an untagged legacy account."""
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
    """Registers and logs in a fresh account, returning its Authorization
    header. For role='lgu_member', pass `permissions` to control access."""
    def _headers(role='admin', permissions=None):
        user = make_user(email=f'{role}@test.com', password='TestPass123', role=role, permissions=permissions)
        res = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = res.get_json()['token']
        return {'Authorization': f'Bearer {token}'}
    return _headers

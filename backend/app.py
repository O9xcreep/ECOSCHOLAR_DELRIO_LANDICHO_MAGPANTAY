# -*- coding: utf-8 -*-
"""Entrypoint: creates/holds the Flask `app` object (via extensions.py),
imports every domain module so their @app.route registrations run, and
re-exports the names backend/tests/*.py and backend/scripts/*.py reach into
directly as app_module.<name> / flask_app.<name> - so this split required no
changes to the test suite or scripts.

gunicorn's `app:app` target (see backend/Dockerfile) is satisfied by the
`app` re-export below.

Import order matters here: each module below imports only from modules
already defined earlier in this chain (extensions -> helpers -> auth ->
documents -> ml_scoring -> admin_settings -> applicants -> notifications ->
memberships -> admin_management -> activity_routes; activity.py itself only
imports extensions, so any of them can log), so there is no circular import - see each
module's own docstring for what it owns."""
import requests
from flask import jsonify
from werkzeug.security import generate_password_hash

from extensions import app, limiter, DEBUG, get_db, _mongo_db  # noqa: F401 (re-exported)

from helpers import (  # noqa: F401 (re-exported for tests/scripts)
    get_default_organization_id, do_program_reset, get_current_cycle_id,
    get_current_cycle, is_cycle_open, income_to_bracket, send_email,
    generate_join_code, GENERIC_REVIEWED_MESSAGE,
    ml_education_map, ml_occupation_categories, ml_housing_situations,
)

import auth  # noqa: F401 - registers /api/login, /api/register, etc.
from auth import _reset_serializer, _admin_apply_serializer  # noqa: F401 (re-exported)

import documents  # noqa: F401 - registers /api/upload, /api/verify-document, etc.
from documents import SELFIE_DOC_LABEL, DEFAULT_DOC_REQUIREMENTS  # noqa: F401 (re-exported)

import ml_scoring  # noqa: F401 - registers /api/applications/<id>/verify, etc.
from ml_scoring import recompute_approvals, build_feature_row, score_with_model  # noqa: F401 (re-exported)

import admin_settings  # noqa: F401 - registers /api/settings, /api/form-fields, etc.
import applicants  # noqa: F401 - registers /api/applicants, /api/apply, etc.
import notifications  # noqa: F401 - registers /api/notifications, etc.
import memberships  # noqa: F401 - registers /api/memberships, /api/organizations/join, /api/organizations/switch, /api/account
from memberships import create_membership_from_approved_request, serialize_membership  # noqa: F401 (re-exported)
import admin_management  # noqa: F401 - registers /api/admins, /api/admin-requests, etc.
import activity_routes  # noqa: F401 - registers /api/activity-logs

# Public, unauthenticated, no DB access - used by uptime pingers to keep the
# free-tier instance awake, and for basic "is it up" checks.
@app.route('/api/health')
def health():
    response = jsonify({"status": "ok"})
    # Cache for 30 seconds to reduce server load
    response.headers['Cache-Control'] = 'public, max-age=30'
    return response

# ── TEST ROUTE ──
@app.route('/api/test')
def test():
    return jsonify({"message": "EcoScholar backend is running!"})

if __name__ == '__main__':
    app.run(debug=DEBUG)

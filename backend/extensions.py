# -*- coding: utf-8 -*-
"""Foundation layer: the Flask app object, CORS, rate limiter, database/GridFS
connections, and env-driven config. Every other module in this package imports
from here - this module must never import from any of them, or the import
chain becomes circular.

Import-order note: backend/tests/conftest.py monkeypatches pymongo.MongoClient
and gridfs.GridFS with mongomock equivalents BEFORE `import app` (and anything
app.py imports) ever runs, specifically so the MongoClient(...)/GridFS(...)
calls below construct fake, in-memory objects during tests instead of trying
to reach a real database. Nothing may import this module (directly or
transitively) before that patch happens."""
import os
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
import gridfs
from dotenv import load_dotenv

# Load .env relative to this file, not the process's working directory - otherwise
# whoever launches the server from a different cwd silently gets no .env at all,
# SECRET_KEY falls back to the dev default, and every previously issued session
# token stops verifying (looks like random, unexplained logouts).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-only-insecure-key'
    else:
        raise RuntimeError('SECRET_KEY environment variable must be set in production')

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
# Sent via an HTTP API (not raw SMTP) because Render's free-tier web services
# block outbound traffic to SMTP ports 25/465/587 - an HTTP API only needs
# normal outbound HTTPS (443), which is never blocked.
#
# EMAIL_PROVIDER picks which one - "resend" (default) or "mailjet". This is a
# temporary switch: Resend's free tier has a sending limit, so ops can flip to
# Mailjet without a code change while that resets, then flip back by just
# changing the env var. Both providers share the same SMTP_FROM_EMAIL/NAME.
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'resend').strip().lower()
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
MAILJET_API_KEY = os.getenv('MAILJET_API_KEY', '')
MAILJET_API_SECRET = os.getenv('MAILJET_API_SECRET', '')
SMTP_FROM_NAME = os.getenv('SMTP_FROM_NAME', 'EcoScholar')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', '')

app = Flask(__name__)
CORS_ORIGINS = [o.strip() for o in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if o.strip()]
CORS(app, supports_credentials=True, origins=CORS_ORIGINS)

limiter = Limiter(get_remote_address, app=app, storage_uri="memory://", default_limits=[])

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'none'"
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains'
    return response

@app.errorhandler(413)
def too_large(e):
    from flask import jsonify
    return jsonify({"error": "File exceeds the 5MB upload limit"}), 413

@app.errorhandler(429)
def rate_limited(e):
    from flask import jsonify
    return jsonify({"error": "Too many attempts. Please wait a minute and try again."}), 429

# ── UPLOAD CONFIG ──
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB, matches the limit shown in the UI
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── DATABASE CONNECTION (MongoDB Atlas) ──
_mongo_client = MongoClient(os.getenv('MONGO_URI'))
_mongo_db = _mongo_client[os.getenv('MONGO_DB_NAME', 'ecoscholars')]
# Uploaded documents live in GridFS (not local disk) so they survive redeploys
# on hosts with ephemeral filesystems.
_fs = gridfs.GridFS(_mongo_db)
# Logged-out tokens land here until their natural expiry so a stolen/leaked token
# can be invalidated before TOKEN_MAX_AGE runs out. TTL index auto-purges entries.
_mongo_db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)
# Registration email-verification codes - same absolute-expiry TTL pattern.
_mongo_db.otps.create_index("expires_at", expireAfterSeconds=0)
# Multi-tenancy, Phase A: join_code is how a future admin/student ends up in the
# right LGU's space (Phase B) - reserve its uniqueness now even though only one
# organization exists yet.
_mongo_db.organizations.create_index("join_code", unique=True)
# require_auth checks this on every authenticated request - without an index
# that's a full collection scan on every single API call in the app.
_mongo_db.revoked_tokens.create_index("token_hash")
_mongo_db.users.create_index("email", unique=True)
_mongo_db.applicants.create_index("organization_id")
_mongo_db.applicants.create_index([("organization_id", 1), ("cycle_id", 1)])
_mongo_db.notifications.create_index([("user_id", 1), ("organization_id", 1)])
_mongo_db.document_requirements.create_index("organization_id")
_mongo_db.program_cycles.create_index("organization_id")
_mongo_db.admin_requests.create_index("organization_id")

def get_db():
    return _mongo_db

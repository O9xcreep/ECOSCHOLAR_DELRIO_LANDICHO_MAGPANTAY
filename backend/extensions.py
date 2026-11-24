# -*- coding: utf-8 -*-
"""Foundation layer: Flask app, CORS, rate limiter, database/GridFS
connections, and env config. Every other module imports from here; this
module must not import from them.

Note: backend/tests/conftest.py patches pymongo.MongoClient and gridfs.GridFS
before importing app.py. This module must only be imported through that
chain, never eagerly by anything else."""
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import gridfs
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-only-insecure-key'
    else:
        raise RuntimeError('SECRET_KEY environment variable must be set in production')

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
# OAuth client ID Google issues ID tokens for - used to verify "Sign in with
# Google" credentials server-side. Same value the frontend uses to render the
# button (VITE_GOOGLE_CLIENT_ID), since a Google ID token's audience must
# match the client ID that requested it.
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
# Email is sent via HTTP API, not SMTP - Render's free tier blocks outbound
# SMTP ports. EMAIL_PROVIDER selects "resend" (default) or "mailjet".
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'resend').strip().lower()
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
MAILJET_API_KEY = os.getenv('MAILJET_API_KEY', '')
MAILJET_API_SECRET = os.getenv('MAILJET_API_SECRET', '')
SMTP_FROM_NAME = os.getenv('SMTP_FROM_NAME', 'EcoScholar')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', '')

# LGUs join by the System Owner's invitation. "true" reopens the public request
# endpoints (anyone with a verified email can ask for an LGU account).
PUBLIC_ADMIN_REQUESTS = os.getenv('PUBLIC_ADMIN_REQUESTS', 'false').strip().lower() == 'true'

app = Flask(__name__)
CORS_ORIGINS = [o.strip() for o in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if o.strip()]
CORS(app, supports_credentials=True, origins=CORS_ORIGINS)

limiter = Limiter(get_remote_address, app=app, storage_uri="memory://", default_limits=[])

@app.after_request
def set_security_headers(response):
    # Skip security headers for health checks (performance optimization)
    if request.path == '/api/health':
        return response

    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Relaxed CSP for API (no need for strict 'none' on JSON responses)
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains'
    return response

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File exceeds the 5MB upload limit"}), 413

@app.errorhandler(429)
def rate_limited(e):
    return jsonify({"error": "Too many attempts. Please wait a minute and try again."}), 429

# MongoDB auth failures: 18 (AuthenticationFailed), 8000 (Atlas "bad auth")
MONGO_AUTH_ERROR_CODES = {18, 8000}

# Without these, a database outage is an HTML 500 that the frontend can't parse
# and reports as a problem with the user's internet connection. Details go to
# the server log only.
@app.errorhandler(ConnectionFailure)
def database_unreachable(e):
    # A rejected login makes pymongo drop that server, so it can surface here as
    # a ServerSelectionTimeoutError with the auth error only in its message.
    if 'authentication failed' in str(e).lower():
        hint = "Database rejected the login - check the credentials in MONGO_URI"
    else:
        hint = "Database unreachable - check the Atlas cluster is running and its IP Access List"
    app.logger.error(hint, exc_info=e)
    return jsonify({"error": "The service is temporarily unavailable. Please try again later."}), 503

@app.errorhandler(OperationFailure)
def database_operation_failed(e):
    if e.code not in MONGO_AUTH_ERROR_CODES:
        raise e
    app.logger.error("Database rejected the login - check the credentials in MONGO_URI", exc_info=e)
    return jsonify({"error": "The service is temporarily unavailable. Please try again later."}), 503

# ── UPLOAD CONFIG ──
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── DATABASE CONNECTION (MongoDB Atlas) ──
# Use serverSelectionTimeoutMS to fail fast if DB is unreachable
_mongo_client = MongoClient(
    os.getenv('MONGO_URI'),
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    retryWrites=False  # Disable retry on free tier to speed up
)
_mongo_db = _mongo_client[os.getenv('MONGO_DB_NAME', 'ecoscholars')]
# Uploaded documents are stored in GridFS, not on local disk.
_fs = gridfs.GridFS(_mongo_db)

def _ensure_indexes():
    """Create indexes only once at startup. MongoDB skips if they exist."""
    try:
        _mongo_db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)
        _mongo_db.otps.create_index("expires_at", expireAfterSeconds=0)
        _mongo_db.organizations.create_index("join_code", unique=True)
        # One account per LGU. Organizations from before this have no location_key.
        _mongo_db.organizations.create_index(
            "location_key",
            unique=True,
            partialFilterExpression={"location_key": {"$type": "string"}},
        )
        _mongo_db.revoked_tokens.create_index("token_hash")
        _mongo_db.users.create_index("email", unique=True)
        _mongo_db.users.create_index("google_id", unique=True, sparse=True)
        _mongo_db.users.create_index(
            "is_system_owner",
            unique=True,
            partialFilterExpression={"is_system_owner": True},
        )
        _mongo_db.applicants.create_index("organization_id")
        _mongo_db.applicants.create_index([("organization_id", 1), ("cycle_id", 1)])
        _mongo_db.notifications.create_index([("user_id", 1), ("organization_id", 1)])
        _mongo_db.document_requirements.create_index("organization_id")
        _mongo_db.program_cycles.create_index("organization_id")
        _mongo_db.admin_requests.create_index("organization_id")
        _mongo_db.memberships.create_index([("user_id", 1), ("organization_id", 1)], unique=True)
        _mongo_db.memberships.create_index("organization_id")
        _mongo_db.activity_logs.create_index([("organization_id", 1), ("created_at", -1)])
        _mongo_db.activity_logs.create_index("created_at")
    except Exception as e:
        print(f"Warning: Could not create indexes: {e}")

# Create indexes on app start (MongoDB dedupes if they exist)
_ensure_indexes()

def get_db():
    return _mongo_db

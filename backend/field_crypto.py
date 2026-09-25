# -*- coding: utf-8 -*-
"""Field-level encryption for applicants' sensitive personal information.

Stored values look like "enc:v1:<base64>" - AES-256-GCM with a fresh random
96-bit nonce per value, so the same address encrypts differently every time
and nothing can be read (or matched) from the database without the key.

Only fields the system never needs to search, sort, or score on are
encrypted (ENCRYPTED_APPLICANT_FIELDS / ENCRYPTED_PROFILE_FIELDS). The ML
inputs (income, family size, GWA, housing, parents' education/occupation)
and the name/course used by search stay readable.

Date of birth is also matched for duplicate detection, which a randomised
ciphertext can't be, so it additionally gets a keyed blind index
(blind_index(): HMAC-SHA256) that equal dates share.

Key: FIELD_ENCRYPTION_KEY (base64 of 32 random bytes). Without one, a key is
derived from SECRET_KEY, so a deploy never goes down for lack of config -
but set a dedicated key in production so rotating SECRET_KEY can't lock the
data. Values encrypted under the derived key stay readable after a dedicated
key is added (decrypt tries both).

decrypt_field() passes anything without the "enc:v1:" prefix through
unchanged, so records written before encryption was added keep working.
Run scripts/encrypt_existing_fields.py once to encrypt those too."""
import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from extensions import SECRET_KEY

PREFIX = 'enc:v1:'

# applicants collection
ENCRYPTED_APPLICANT_FIELDS = ('contact_number', 'address', 'date_of_birth', 'religion',
                              'father_name', 'mother_name')
# users collection (registration profile, reused to prefill the application form)
ENCRYPTED_PROFILE_FIELDS = ('contactNumber', 'address', 'dob', 'religion', 'fatherName', 'motherName')


def _derive(info):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(SECRET_KEY.encode())


def _load_keys():
    derived = _derive(b'ecoscholar-field-encryption')
    raw = os.getenv('FIELD_ENCRYPTION_KEY', '').strip()
    if not raw:
        return derived, [derived]
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError('FIELD_ENCRYPTION_KEY must be base64 of exactly 32 bytes')
    return key, [key, derived]


_ENCRYPT_KEY, _DECRYPT_KEYS = _load_keys()
_INDEX_KEY = hashlib.sha256(b'ecoscholar-blind-index' + _ENCRYPT_KEY).digest()


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt_field(value):
    """Encrypts a non-empty value; None/'' and already-encrypted values pass through."""
    if value is None or value == '' or is_encrypted(value):
        return value
    nonce = os.urandom(12)
    ciphertext = AESGCM(_ENCRYPT_KEY).encrypt(nonce, str(value).encode('utf-8'), None)
    return PREFIX + base64.b64encode(nonce + ciphertext).decode('ascii')


def decrypt_field(value):
    """Decrypts an "enc:v1:" value; anything else (legacy plaintext, None) is returned as-is."""
    if not is_encrypted(value):
        return value
    blob = base64.b64decode(value[len(PREFIX):])
    nonce, ciphertext = blob[:12], blob[12:]
    for key in _DECRYPT_KEYS:
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, None).decode('utf-8')
        except Exception:
            continue
    raise ValueError('Encrypted field could not be decrypted with the configured key')


def blind_index(value):
    """Deterministic keyed hash for equality matching on an encrypted field."""
    if value is None or value == '':
        return None
    normalized = str(value).strip().lower()
    return hmac.new(_INDEX_KEY, normalized.encode('utf-8'), hashlib.sha256).hexdigest()


def encrypt_fields(doc, fields):
    """Returns a copy of doc with the given fields encrypted."""
    out = dict(doc)
    for f in fields:
        if f in out:
            out[f] = encrypt_field(out[f])
    return out


def decrypt_fields(doc, fields):
    """Returns a copy of doc with the given fields decrypted."""
    out = dict(doc)
    for f in fields:
        if f in out:
            out[f] = decrypt_field(out[f])
    return out

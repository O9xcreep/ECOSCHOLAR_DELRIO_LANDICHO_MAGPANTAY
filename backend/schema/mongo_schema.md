# MongoDB collections

Migrated from the MySQL schema in `schema.sql` (kept there for reference).
8 SQL tables collapsed into 4 collections, since MongoDB has no joins and
most of the old tables were always queried scoped to a single applicant:

- **`users`** — `full_name`, `email` (should be unique), `password` (hashed),
  `role` (`admin`|`student`), `status`, `created_at`, `privacy_consent`.

- **`applicants`** — everything about one scholarship applicant in a single
  document, since `academic_info` and `applications` were always 1:1 with an
  applicant, and `documents`/`audit_trail` were always queried scoped to one:
  - top-level applicant fields (name, contact info, family info, etc.)
  - `user_id` — ObjectId ref into `users` (the account that submitted it)
  - `academic` — subdocument (school, course, year_level, gpa, ...)
  - `application` — subdocument (status, submitted_at, reviewed_at, ...)
  - `documents` — array of `{document_name, file_path, status, uploaded_at}`
  - `audit_trail` — array of `{action, performed_by, old_status, new_status, ...}`

- **`duplicate_flags`** — stays top-level since the admin dashboard lists
  unresolved flags across *all* applicants at once (`applicant_id` and
  `duplicate_of_id` are ObjectId refs into `applicants`).

- **`notifications`** — stays top-level since it's queried per logged-in
  user, not per applicant (`user_id` ref into `users`, `applicant_id` ref
  into `applicants`).

All IDs are Mongo `ObjectId`s, serialized to their string form (`str(id)`) in
every API response — the frontend always treated ids as opaque strings, so
this required no frontend changes.

## Indexes

- `users.email` — unique (mirrors the old MySQL `UNIQUE KEY email`)
- `applicants.email`, `applicants.user_id` — lookups in `/api/apply` duplicate
  checks and `/api/student/application`
- `notifications.user_id` — every notification read is scoped to one user
- `duplicate_flags.resolved` — the admin dashboard always filters on this

Re-create them with:
```
python -c "
from pymongo import MongoClient; import os; from dotenv import load_dotenv
load_dotenv(); db = MongoClient(os.getenv('MONGO_URI'))[os.getenv('MONGO_DB_NAME','ecoscholars')]
db.users.create_index('email', unique=True)
db.applicants.create_index('email'); db.applicants.create_index('user_id')
db.notifications.create_index('user_id'); db.duplicate_flags.create_index('resolved')
"
```

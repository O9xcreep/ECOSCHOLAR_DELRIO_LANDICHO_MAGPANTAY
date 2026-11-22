# MongoDB collections

Migrated from the MySQL schema in `schema.sql` (kept there for reference).
Applicant-related tables were consolidated into applicant documents; separate
collections support organization-scoped identity, membership, and operations:

- **`users`** — `full_name`, `email` (unique), `password` (hashed), `role`
  (`student`, `lgu_member`, or `lgu_admin`), `organization_id` (active
  organization), `status`, `created_at`, and `privacy_consent`. The single
  System Owner is an active `lgu_admin` with `is_system_owner: true` and
  `system_owner_organization_id` set to the organization where the role applies.
  Legacy `admin` accounts are retired and cannot sign in.
- **`organizations`** — `name`, `municipality`, unique `join_code`, and
  `status` (`pending` or `active`).
- **`memberships`** — one `{user_id, organization_id}` record per user's
  organization membership, with its own `role`, permissions, and municipality.
  This is the source of truth when an account belongs to more than one
  organization.

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
- `users.is_system_owner` — unique partial index for documents where the
  value is `true`, enforcing one designated System Owner.
- `memberships.user_id, memberships.organization_id` — unique compound index.
- `organizations.join_code` — unique.
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
db.users.create_index('is_system_owner', unique=True, partialFilterExpression={'is_system_owner': True})
db.organizations.create_index('join_code', unique=True)
db.memberships.create_index([('user_id', 1), ('organization_id', 1)], unique=True)
db.applicants.create_index('email'); db.applicants.create_index('user_id')
db.notifications.create_index('user_id'); db.duplicate_flags.create_index('resolved')
"
```

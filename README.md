# EcoScholar

Centralized Scholarship Allocation & Automated Disbursement System — a scholarship
application portal for students and administrators, with ML-assisted eligibility
scoring and OCR-based document verification.

## Stack

- **Backend**: Flask (Python), MongoDB Atlas (via `pymongo` + GridFS for uploaded
  documents), Tesseract OCR, a combined XGBoost classifier + Random Forest
  regressor for eligibility scoring
- **Frontend**: React + Vite, plain JS
- **Deployment**: backend on Render (Docker), frontend on Vercel

## Local development

### Backend
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Needs a `.env` file (see `backend/.env.example`) with your MongoDB Atlas
connection string and a `SECRET_KEY`. Requires Tesseract OCR installed locally
for document verification/autofill (set `TESSERACT_CMD` if it's not at the
default Windows path).

### Frontend
```powershell
cd frontend
npm install
npm run dev
```
Runs at `http://localhost:5173`. Talks to the backend via `VITE_API_URL`
(see `frontend/.env.example`); defaults to `http://127.0.0.1:5000` for local dev.

## Demo accounts

- Admin: `admin@ecoscolar.edu.ph` / `admin123`
- Student: `student@gmail.com` / `student123`

## Repo layout

- `backend/app.py` — the whole API (auth, applications, documents, ML scoring,
  notifications)
- `backend/ocr.py` — text extraction (Tesseract) and document verification/autofill
- `backend/ecoscholar_*.joblib`, `ecoscholar_*.json`, `ecoscholar_predict.py` —
  the trained eligibility model bundle (see `backend/schema/ml_model.md` for
  its exact feature schema and encoding)
- `backend/schema/` — DB schema docs and the ML model contract
- `backend/scripts/` — one-off migration/seed scripts
- `frontend/src/pages/admin/` and `frontend/src/pages/student/` — the two portals

FROM python:3.13-slim

# Tesseract (OCR) and poppler-utils (pdf2image's PDF->image conversion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Tesseract lives on PATH in this image (not the Windows path baked into ocr.py's default)
ENV TESSERACT_CMD=/usr/bin/tesseract
# Tesseract otherwise starts one OpenMP thread per visible core, and on a host
# with a fractional CPU share (Render free) those threads just fight each other
# and slow every OCR run down.
ENV OMP_THREAD_LIMIT=1

EXPOSE 5000
# Render (and most PaaS hosts) inject $PORT at runtime - the app must bind to
# that, not a hardcoded port. Shell form so $PORT actually expands.
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 app:app

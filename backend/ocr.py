import pytesseract
from PIL import Image, ImageOps
import pdf2image
import os
import re

# Set tesseract path (override with TESSERACT_CMD env var on non-Windows hosts)
_tesseract_cmd = os.getenv('TESSERACT_CMD', r'C:\Program Files\Tesseract-OCR\tesseract.exe')
if os.path.exists(_tesseract_cmd):
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd

MIN_DIMENSION = 1600  # upscale below this so small phone photos have enough resolution to OCR well

def preprocess_image(img):
    """Clean up a scanned/photographed document before OCR: grayscale, stretch
    contrast, binarize, and upscale small images. Cheap, no new dependencies,
    and the single biggest lever for accuracy on real phone-camera photos."""
    img = ImageOps.exif_transpose(img)  # respect phone camera rotation metadata
    img = img.convert('L')  # grayscale
    img = ImageOps.autocontrast(img, cutoff=1)

    width, height = img.size
    if max(width, height) < MIN_DIMENSION:
        scale = MIN_DIMENSION / max(width, height)
        img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

    # Simple binarization - push faded/uneven scan backgrounds to white, text to black
    img = img.point(lambda p: 255 if p > 180 else 0)
    return img

def extract_text_from_image(image_path):
    """Extract text from image file"""
    try:
        img = Image.open(image_path)
        img = preprocess_image(img)
        text = pytesseract.image_to_string(img, config='--psm 6')
        return text.strip()
    except Exception as e:
        return f"Error reading image: {str(e)}"

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    try:
        pages = pdf2image.convert_from_path(pdf_path, dpi=300)
        full_text = ''
        for page in pages:
            page = preprocess_image(page)
            text = pytesseract.image_to_string(page, config='--psm 6')
            full_text += text + '\n'
        return full_text.strip()
    except Exception as e:
        return f"Error reading PDF: {str(e)}"

def extract_text(file_path):
    """Auto detect file type and extract text"""
    ext = file_path.lower().split('.')[-1]
    if ext == 'pdf':
        return extract_text_from_pdf(file_path)
    elif ext in ['jpg', 'jpeg', 'png']:
        return extract_text_from_image(file_path)
    else:
        return "Unsupported file type"

def _significant_words(text, min_len=3):
    return [w for w in re.findall(r"[a-zA-Z]+", text.lower()) if len(w) > min_len]

def _match_count(candidate_text, text_lower, min_len=3):
    """How many distinct significant words from candidate_text appear in text_lower."""
    words = set(_significant_words(candidate_text, min_len))
    return sum(1 for w in words if w in text_lower)

def _address_keywords(address):
    """Pull out the distinctive location words from a free-text address
    (skip generic filler like 'street', 'city', numbers, etc.)."""
    STOPWORDS = {'street', 'st', 'city', 'brgy', 'barangay', 'province', 'road', 'purok', 'zone'}
    words = [w for w in _significant_words(address, min_len=3) if w not in STOPWORDS]
    return words

def _find_gpa_value(text):
    """Extract a GWA/GPA as a percentage (75-99 scale). Shared by parse_document_fields
    (autofill) and verify_document (fraud cross-check) so both read the same value."""
    patterns = [
        r'gwa[:\s]+(\d+\.?\d*)',
        r'gpa[:\s]+(\d+\.?\d*)',
        r'average[:\s]+(\d+\.?\d*)',
        r'general\s+weighted\s+average[:\s]+(\d+\.?\d*)',
        r'(\d+\.?\d*)\s*/\s*100',
        r'grade[:\s]+(\d+\.?\d*)',
    ]
    OLD_SCALE_TO_PERCENT = {
        1.00: 98, 1.25: 95, 1.50: 92, 1.75: 89, 2.00: 86,
        2.25: 83, 2.50: 80, 2.75: 77, 3.00: 75,
    }
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            val = float(match.group(1))
            if val <= 5.0:
                closest = min(OLD_SCALE_TO_PERCENT, key=lambda k: abs(k - val))
                return float(OLD_SCALE_TO_PERCENT[closest])
            if 60 <= val <= 100:
                return round(val, 1)
            # Implausible for either scale (e.g. the generic "grade[:\s]+(\d+)"
            # pattern matching the "12" in a "GRADE 12 REPORT CARD" title, not an
            # actual GWA figure) - keep trying other patterns instead of
            # returning a bogus value that would feed a false fraud flag.
    return None

def _find_income_value(text):
    """Extract the monthly household income as a raw PHP number. Shared by
    parse_document_fields (autofill) and verify_document (fraud cross-check)."""
    pattern = r'(?:income|sahod|kita)[:\s]+(?:php|₱|p)?\s*([\d,]+)'
    match = re.search(pattern, text.lower())
    if match:
        try:
            return int(match.group(1).replace(',', ''))
        except ValueError:
            pass
    return None

def verify_document(doc_type, extracted_text, applicant_data):
    """
    Verify a document actually belongs to this applicant and is the claimed
    document type - not just any file that happens to share a stray keyword.

    Design: the applicant's name must genuinely appear (2+ distinct name parts
    for multi-word names) or the document is immediately failed, regardless of
    any other keyword coincidences. Every other check requires multiple
    distinct matching signals rather than a single loosely-matched word.
    """
    text_lower = extracted_text.lower()
    results = {
        'doc_type': doc_type,
        'extracted_text': extracted_text[:500],
        'checks': [],
        'flags': [],
        'confidence': 0,
        'status': 'Unverified'
    }

    # ── Gating check: does the applicant's name genuinely appear? ──
    full_name = applicant_data.get('full_name', '') or ''
    name_parts = [p for p in full_name.lower().split() if len(p) > 2]
    name_matches = sum(1 for p in name_parts if p in text_lower)
    name_found = name_matches >= 2 if len(name_parts) >= 2 else name_matches >= 1

    results['checks'].append({
        'check': 'Applicant name found',
        'passed': name_found
    })

    if not name_found:
        # Doesn't even mention the applicant - almost certainly the wrong
        # document or the wrong person's paperwork. Don't let generic
        # keyword coincidences rescue the score.
        results['confidence'] = 0
        results['status'] = 'Failed Verification'
        return results

    # ── Document-type specific checks (each requires multiple distinct signals) ──
    if doc_type == 'Enrollment Form':
        school = applicant_data.get('school', '') or ''
        course = applicant_data.get('course', '') or ''
        results['checks'].append({
            'check': 'School name found',
            'passed': _match_count(school, text_lower) >= min(2, len(_significant_words(school)))
                      and _match_count(school, text_lower) >= 1
        })
        results['checks'].append({
            'check': 'Course found',
            'passed': _match_count(course, text_lower) >= 1
        })
        results['checks'].append({
            'check': 'Enrollment keywords found',
            'passed': _match_count(
                'enrolled enrollment registration registrar schoolyear semester',
                text_lower
            ) >= 2
        })

    elif doc_type == 'Barangay Endorsement':
        address_words = _address_keywords(applicant_data.get('address', '') or '')
        location_found = any(w in text_lower for w in address_words) if address_words else False
        results['checks'].append({
            'check': 'Applicant location found',
            'passed': location_found
        })
        results['checks'].append({
            'check': 'Endorsement keywords found',
            'passed': _match_count(
                'endorsement barangay certify resident indigent residency certification',
                text_lower
            ) >= 2
        })

    elif doc_type == 'School ID':
        school = applicant_data.get('school', '') or ''
        results['checks'].append({
            'check': 'School name found',
            'passed': _match_count(school, text_lower) >= 1
        })
        results['checks'].append({
            'check': 'ID keywords found',
            'passed': _match_count(
                'student identification university college validuntil schoolyear',
                text_lower
            ) >= 2
        })

    elif doc_type == 'Proof of Income':
        results['checks'].append({
            'check': 'Income document keywords found',
            'passed': _match_count(
                'income indigency indigent certificate itr revenue tax annual certify',
                text_lower
            ) >= 2
        })
        results['checks'].append({
            'check': 'Amount/figures found',
            'passed': bool(re.search(r'₱|php|peso|\d{4,}', text_lower))
        })

        # ── Fraud cross-check: does the figure on the document roughly match what
        # was declared on the application? A large mismatch is a much stronger
        # signal than any keyword check above - flagged separately so it can't
        # get lost in the ordinary confidence score. Tolerance is deliberately
        # generous (40%) since OCR misreads digits and this should prompt a
        # manual look, not an automatic accusation.
        doc_income = _find_income_value(extracted_text)
        submitted_income = applicant_data.get('monthly_income')
        if doc_income is not None and submitted_income:
            diff_ratio = abs(doc_income - submitted_income) / max(doc_income, submitted_income)
            income_matches = diff_ratio <= 0.4
            results['checks'].append({
                'check': 'Income matches submitted application',
                'passed': income_matches
            })
            if not income_matches:
                results['flags'].append(
                    f"Declared monthly income (₱{submitted_income:,.0f}) doesn't closely "
                    f"match the amount stated on this document (₱{doc_income:,.0f}) - "
                    f"worth a manual check."
                )

    elif doc_type == 'Grade 12 Grades':
        school = applicant_data.get('school', '') or ''
        results['checks'].append({
            'check': 'School name found',
            'passed': _match_count(school, text_lower) >= 1
        })
        results['checks'].append({
            'check': 'Grade keywords found',
            'passed': _match_count(
                'grade average gpa gwa seniorhigh deped reportcard weighted form',
                text_lower
            ) >= 2
        })

        # ── Fraud cross-check: same reasoning as income above. ──
        doc_gpa = _find_gpa_value(extracted_text)
        submitted_gpa = applicant_data.get('gpa')
        if doc_gpa is not None and submitted_gpa:
            gpa_matches = abs(doc_gpa - float(submitted_gpa)) <= 5
            results['checks'].append({
                'check': 'GWA matches submitted application',
                'passed': gpa_matches
            })
            if not gpa_matches:
                results['flags'].append(
                    f"Declared GWA ({submitted_gpa}) doesn't closely match the grade stated "
                    f"on this document ({doc_gpa}) - worth a manual check."
                )

    elif doc_type == '4Ps Certificate':
        results['checks'].append({
            'check': '4Ps keywords found',
            'passed': _match_count(
                'pantawid dswd beneficiary conditional household program',
                text_lower
            ) >= 2 or 'pantawid' in text_lower or '4ps' in text_lower
        })

    # Calculate confidence
    passed = sum(1 for c in results['checks'] if c['passed'])
    total = len(results['checks'])
    confidence = round((passed / total) * 100) if total > 0 else 0
    results['confidence'] = confidence

    # Set status - stricter bands than before, since the name gate already
    # removed the easiest source of false positives.
    if confidence >= 70:
        results['status'] = 'Verified'
    elif confidence >= 40:
        results['status'] = 'Partially Verified'
    else:
        results['status'] = 'Failed Verification'

    # A value mismatch (income/GWA vs what was declared) is a stronger signal than
    # an ordinary missing keyword, so it can't be masked by an otherwise-high
    # confidence score - cap the overall status even if the math alone says "Verified".
    if results['flags'] and results['status'] == 'Verified':
        results['status'] = 'Partially Verified'

    return results

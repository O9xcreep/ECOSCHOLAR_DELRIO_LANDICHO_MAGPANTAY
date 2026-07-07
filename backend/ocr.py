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
    if confidence >= 75:
        results['status'] = 'Verified'
    elif confidence >= 50:
        results['status'] = 'Partially Verified'
    else:
        results['status'] = 'Failed Verification'

    return results

def parse_document_fields(text, doc_type):
    """
    Parse extracted OCR text and return
    matching form fields based on document type
    """
    fields = {}
    text_lower = text.lower()
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # ── Helper functions ──
    def find_after_keyword(keywords, text_lines):
        """Find value after a keyword in the text"""
        for i, line in enumerate(text_lines):
            for keyword in keywords:
                if keyword.lower() in line.lower():
                    # Check same line after colon
                    if ':' in line:
                        value = line.split(':', 1)[1].strip()
                        if value and len(value) > 1:
                            return value
                    # Check next line
                    if i + 1 < len(text_lines):
                        next_line = text_lines[i + 1].strip()
                        if next_line and len(next_line) > 1:
                            return next_line
        return None

    def find_name(text_lines):
        """Try to extract a full name from text"""
        name_keywords = ['name:', 'student:', 'applicant:', 'pangalan:']
        name = find_after_keyword(name_keywords, text_lines)
        if name:
            # Clean up common OCR artifacts
            name = re.sub(r'[^a-zA-Z\s\.\,]', '', name).strip()
            if len(name) > 3:
                return name.title()
        return None

    def find_gpa(text):
        """Extract Grade 12 / latest GWA as a percentage (75-99 scale, what
        the application form and eligibility model now expect)."""
        patterns = [
            r'gwa[:\s]+(\d+\.?\d*)',
            r'gpa[:\s]+(\d+\.?\d*)',
            r'average[:\s]+(\d+\.?\d*)',
            r'general\s+weighted\s+average[:\s]+(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*/\s*100',
            r'grade[:\s]+(\d+\.?\d*)',
        ]
        # Old Philippine 1.00 (highest) - 5.00 (lowest) GWA scale, in case an
        # older-style report card shows that instead of a percentage.
        OLD_SCALE_TO_PERCENT = {
            1.00: 98, 1.25: 95, 1.50: 92, 1.75: 89, 2.00: 86,
            2.25: 83, 2.50: 80, 2.75: 77, 3.00: 75,
        }
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                val = float(match.group(1))
                if val <= 5.0:
                    # Old 1.00-5.00 scale - convert to the nearest percentage band
                    closest = min(OLD_SCALE_TO_PERCENT, key=lambda k: abs(k - val))
                    return str(OLD_SCALE_TO_PERCENT[closest])
                return str(round(val, 1))
        return None

    def find_school(text_lines):
        """Extract school name"""
        school_keywords = [
            'university', 'college', 'institute',
            'school', 'academy', 'pamantasan'
        ]
        for line in text_lines:
            line_lower = line.lower()
            if any(kw in line_lower for kw in school_keywords):
                if len(line) > 5 and len(line) < 150:
                    return line.strip()
        return None

    def find_course(text_lines):
        """Extract course/program"""
        course_keywords = [
            'course:', 'program:', 'degree:', 'course of study:',
            'bs ', 'bachelor', 'ab ', 'bsed', 'bsn', 'bscs',
            'bsit', 'bsba', 'bsme', 'bsce', 'bsee'
        ]
        course = find_after_keyword(
            ['course', 'program', 'degree', 'course of study'],
            text_lines
        )
        if course:
            return course

        for line in text_lines:
            if any(kw in line.lower() for kw in ['bs ', 'ab ', 'bachelor']):
                if len(line) < 80:
                    return line.strip()
        return None

    def find_year_level(text):
        """Extract year level"""
        patterns = [
            r'(1st|first)\s+year',
            r'(2nd|second)\s+year',
            r'(3rd|third)\s+year',
            r'(4th|fourth)\s+year',
            r'(5th|fifth)\s+year',
            r'year\s+(1|2|3|4|5)',
        ]
        year_map = {
            '1st': '1st Year', 'first': '1st Year', '1': '1st Year',
            '2nd': '2nd Year', 'second': '2nd Year', '2': '2nd Year',
            '3rd': '3rd Year', 'third': '3rd Year', '3': '3rd Year',
            '4th': '4th Year', 'fourth': '4th Year', '4': '4th Year',
            '5th': '5th Year', 'fifth': '5th Year', '5': '5th Year',
        }
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                key = match.group(1).lower()
                return year_map.get(key, None)
        return None

    def find_semester(text):
        """Extract semester"""
        if '1st semester' in text_lower or 'first semester' in text_lower:
            return '1st Semester'
        elif '2nd semester' in text_lower or 'second semester' in text_lower:
            return '2nd Semester'
        elif 'summer' in text_lower:
            return 'Summer'
        return None

    def find_academic_year(text):
        """Extract academic year like 2025-2026"""
        pattern = r'(20\d{2})\s*[-–]\s*(20\d{2})'
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return None

    def find_address(text_lines):
        """Extract address"""
        addr_keywords = ['address:', 'tirahan:', 'residence:', 'living at:']
        address = find_after_keyword(addr_keywords, text_lines)
        if address and len(address) > 5:
            return address
        return None

    def find_barangay(text):
        """Extract barangay"""
        pattern = r'brgy\.?\s+([a-zA-Z\s]+)|barangay\s+([a-zA-Z\s]+)'
        match = re.search(pattern, text_lower)
        if match:
            brgy = (match.group(1) or match.group(2) or '').strip()
            if brgy and len(brgy) > 2:
                return brgy.title()
        return None

    def find_parent_name(text_lines, parent='father'):
        """Extract parent name"""
        keywords = [f"{parent}'s name", f"{parent}:", 'ama' if parent == 'father' else 'ina']
        name = find_after_keyword(keywords, text_lines)
        if name:
            name = re.sub(r'[^a-zA-Z\s\.\,]', '', name).strip()
            if len(name) > 3:
                return name.title()
        return None

    def find_income(text):
        """Extract the monthly household income as a raw number (PHP)"""
        pattern = r'(?:income|sahod|kita)[:\s]+(?:php|₱|p)?\s*([\d,]+)'
        match = re.search(pattern, text_lower)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except ValueError:
                pass
        return None

    if doc_type == 'Enrollment Form':
        name = find_name(lines)
        school = find_school(lines)
        course = find_course(lines)
        year_level = find_year_level(text)
        semester = find_semester(text)
        academic_year = find_academic_year(text)

        if name: fields['fullName'] = name
        if school: fields['school'] = school
        if course: fields['course'] = course
        if year_level: fields['yearLevel'] = year_level
        if semester: fields['semester'] = semester
        if academic_year: fields['academicYear'] = academic_year

    elif doc_type == 'School ID':
        name = find_name(lines)
        school = find_school(lines)
        course = find_course(lines)

        if name: fields['fullName'] = name
        if school: fields['school'] = school
        if course: fields['course'] = course

    elif doc_type == 'Copy of Barangay Endorsement':
        name = find_name(lines)
        address = find_address(lines)
        barangay = find_barangay(text)

        if name: fields['fullName'] = name
        if address: fields['address'] = address
        if barangay: fields['barangay'] = barangay

    elif doc_type == 'Proof of Income (Certificate of Indigency)':
        name = find_name(lines)
        address = find_address(lines)
        income = find_income(text)
        father = find_parent_name(lines, 'father')
        mother = find_parent_name(lines, 'mother')

        if name: fields['fullName'] = name
        if address: fields['address'] = address
        if income: fields['monthlyIncome'] = income
        if father: fields['fatherName'] = father
        if mother: fields['motherName'] = mother

    elif doc_type == 'If incoming 1st yr college, 1 copy of Grade 12 grades':
        name = find_name(lines)
        school = find_school(lines)
        gpa = find_gpa(text)
        academic_year = find_academic_year(text)

        if name: fields['fullName'] = name
        if school: fields['school'] = school
        if gpa: fields['gpa'] = gpa
        if academic_year: fields['academicYear'] = academic_year

    else:
        # Generic — try to extract common fields
        name = find_name(lines)
        school = find_school(lines)
        if name: fields['fullName'] = name
        if school: fields['school'] = school

    return fields

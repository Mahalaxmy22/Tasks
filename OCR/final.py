

import io
import re
from datetime import datetime, date
from typing import Tuple, List, Optional, Dict, Any

import streamlit as st
from PIL import Image
import fitz  
import numpy as np
import mysql.connector

try:
    from paddleocr import PaddleOCR
except Exception:
    PaddleOCR = None

try:
    import easyocr
except Exception:
    easyocr = None

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="maha",
        database="aadhaar_db"
    )

def init_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS aadhar_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255),
            father_name VARCHAR(255),
            dob DATE,
            age INT
        );
    """)
    conn.commit()
    conn.close()

init_table()

def calculate_age(dob_date: date) -> int:
    today = date.today()
    return today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))

def fitz_page_to_pil(page: fitz.Page) -> Image.Image:
    pix = page.get_pixmap(dpi=300)
    mode = "RGB" if pix.n < 4 else "RGBA"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)

def resize_for_ocr(img: Image.Image, target_w: int = 1400) -> Image.Image:
    w, h = img.size
    if w >= target_w:
        return img
    r = target_w / float(w)
    return img.resize((target_w, int(h * r)), Image.LANCZOS)

def get_paddle_reader():
    if PaddleOCR is None:
        return None
    if "paddle_reader_ta" not in st.session_state:
        st.session_state.paddle_reader_ta = PaddleOCR(use_angle_cls=True, lang="ta")
    return st.session_state.paddle_reader_ta

def ocr_with_paddle(img: Image.Image) -> str:
    reader = get_paddle_reader()
    if reader is None:
        return ""
    arr = np.array(img.convert("RGB"))
    results = reader.ocr(arr)
    lines: List[str] = []
    for page in results:
        for item in page:
            txt = item[1][0] if isinstance(item[1], (list, tuple)) else str(item[1])
            lines.append(txt)
    return "\n".join(lines)

def get_easy_reader_en():
    if easyocr is None:
        return None
    if "easy_reader_en" not in st.session_state:
        st.session_state.easy_reader_en = easyocr.Reader(["en"], gpu=False)
    return st.session_state.easy_reader_en

def ocr_with_easy_en(img: Image.Image) -> str:
    reader = get_easy_reader_en()
    if reader is None:
        return ""
    arr = np.array(img.convert("RGB"))
    results = reader.readtext(arr)
    results_sorted = sorted(results, key=lambda x: x[0][0][1])
    return "\n".join([r[1] for r in results_sorted])

def run_hybrid_ocr_on(img: Image.Image) -> str:
    img2 = resize_for_ocr(img, target_w=1400)
    paddle_text = ocr_with_paddle(img2) if PaddleOCR is not None else ""
    easy_text = ocr_with_easy_en(img2) if easyocr is not None else ""
    merged = "\n".join([t for t in (paddle_text, easy_text) if t])
    return merged.strip()

def candidate_crops(img: Image.Image) -> Dict[str, Image.Image]:
    w, h = img.size
    crops = {
        "photo_right": img.crop((int(w * 0.18), int(h * 0.28), int(w * 0.98), int(h * 0.75))),
        "top_left": img.crop((0, 0, int(w * 0.65), int(h * 0.40))),
        "bottom_center": img.crop((int(w * 0.02), int(h * 0.45), int(w * 0.98), int(h * 0.90))),
        "full": img.copy()
    }
    return crops

def score_text_usefulness(text: str) -> int:
    alpha = len(re.findall(r"[A-Za-z]", text))
    good_lines = sum(1 for l in text.splitlines() if len(re.findall(r"[A-Za-z]{2,}", l)) >= 2)
    return alpha + good_lines * 40

def extract_best_text_from_image(img: Image.Image) -> Tuple[str, Dict[str, Any]]:
    crops = candidate_crops(img)
    scored = {}
    for label, crop in crops.items():
        txt = run_hybrid_ocr_on(crop)
        scored[label] = {"text": txt, "score": score_text_usefulness(txt)}
    sorted_items = sorted(scored.items(), key=lambda kv: kv[1]["score"], reverse=True)
    merged = ""
    meta = {"ranked": []}
    for i, (label, info) in enumerate(sorted_items[:2]):  
        if i == 0:
            merged = info["text"]
        else:
            merged += "\n" + info["text"]
        meta["ranked"].append({"label": label, "score": info["score"]})
    return merged.strip(), meta

def extract_text_from_file(uploaded_file) -> Tuple[str, Dict[str, Any]]:
    ftype = uploaded_file.type.lower()
    pages_meta = []
    texts = []
    if "pdf" in ftype:
        pdf = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        for pno in range(pdf.page_count):
            page = pdf.load_page(pno)
            pil = fitz_page_to_pil(page)
            txt, meta = extract_best_text_from_image(pil)
            texts.append(txt)
            pages_meta.append({"page": pno, "meta": meta})
    else:
        try:
            pil = Image.open(uploaded_file).convert("RGB")
        except Exception:
            uploaded_file.seek(0)
            pil = Image.open(io.BytesIO(uploaded_file.read())).convert("RGB")
        txt, meta = extract_best_text_from_image(pil)
        texts.append(txt)
        pages_meta.append({"page": 0, "meta": meta})
    return "\n\n".join(texts), {"pages": pages_meta}

def parse_date_string(date_str: str) -> Optional[date]:
    s = date_str.strip()
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except:
            pass
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except:
            pass
    return None

def robust_parse_aadhar(text: str) -> Tuple[str, str, str, int, Dict[str, Any]]:
    """
    Returns (name, father, dob_str, age, debug_meta)
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = ""
    father = ""
    dob = ""
    age = 0
    candidate_dates = []
    dob_labels = ["dob", "date of birth", "birth", "பிறந்த", "பிறந்த நாள்"]

    for i, line in enumerate(lines):
        low = line.lower()

        fm = re.search(r"(s/o|d/o|c/o|father|தந்தை|பிதா)[:\s]*([A-Za-z ]+)", line, re.IGNORECASE)
        if fm and not father:
            cand = re.sub(r"[^A-Za-z ]", "", fm.group(2)).strip()
            if len(cand.split()) >= 1:
                father = cand.title()

        m_name = re.search(r"^name[:\-\s]*([A-Za-z ]{2,})$", line, re.IGNORECASE)
        if m_name and not name:
            cand = re.sub(r"[^A-Za-z ]", "", m_name.group(1)).strip()
            if len(cand.split()) >= 2:
                name = cand.title()

        if low.startswith("to") and not name:
            for j in range(i+1, min(i+4, len(lines))):
                cand = re.sub(r"[^A-Za-z ]", "", lines[j]).strip()
                if len(cand.split()) >= 2:
                    name = cand.title()
                    break

        found_dates = re.findall(r'(\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b|\b\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}\b|\b[A-Za-z]{3,}\s+\d{1,2},\s*\d{4}\b|\b\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}\b)', line)
        for dstr in found_dates:
            parsed = parse_date_string(dstr)
            if parsed:
                pr = 2 if any(lbl in low for lbl in dob_labels) else 0
                if re.search(r'enrol|enrollment|issue date|download date', low):
                    pr = min(pr, 0)
                candidate_dates.append((parsed, line, pr))

    dob_meta = []
    if candidate_dates:
        def score_dt(tup):
            dt, line, pr = tup
            try:
                a = calculate_age(dt)
            except:
                a = 999
            plaus = 0
            if 3 <= a <= 120:
                plaus = 10
            if 16 <= a <= 80:
                plaus += 5
            return (pr, plaus, -dt.toordinal())
        candidate_dates_sorted = sorted(candidate_dates, key=score_dt, reverse=True)
        chosen = candidate_dates_sorted[0][0]
        final_age = calculate_age(chosen)
        if 0 <= final_age <= 120:
            dob = chosen.strftime("%d/%m/%Y")
            age = final_age
        dob_meta = [{"date": d.strftime("%d/%m/%Y"), "line": ln, "prio": pr} for (d, ln, pr) in candidate_dates_sorted[:5]]

    if not dob:
        loose = re.findall(r'(\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b|\b\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}\b)', text)
        pcands = []
        for dstr in loose:
            parsed = parse_date_string(dstr)
            if parsed:
                a = calculate_age(parsed)
                if 3 <= a <= 120:
                    pcands.append((parsed, a))
        if pcands:
            pcands.sort(key=lambda x: (x[1] >= 16, -x[1]), reverse=True)
            chosen = pcands[0][0]
            dob = chosen.strftime("%d/%m/%Y")
            age = calculate_age(chosen)

    if not name:
        for line in lines:
            cl = re.sub(r'[^A-Za-z ]', ' ', line).strip()
            if len(cl.split()) >= 2 and not any(k in cl.lower() for k in ["government", "india", "enrol", "address", "dob"]):
                if father and father.lower() in cl.lower():
                    continue
                name = cl.title()
                break

    debug = {"lines_count": len(lines), "candidate_dates": dob_meta}
    return name.strip(), father.strip(), dob, age, debug

def save_record(name: str, father: str, dob: str, age: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    dob_sql = None
    if dob:
        try:
            dob_sql = datetime.strptime(dob, "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            dob_sql = None
    cur.execute("INSERT INTO aadhar_data (name, father_name, dob, age) VALUES (%s, %s, %s, %s)", (name, father, dob_sql, age))
    conn.commit()
    conn.close()

def load_records(limit: int = 200):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, father_name, dob, age FROM aadhar_data ORDER BY id DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

st.set_page_config(page_title="Aadhaar ocr", layout="centered")
st.title("Aadhaar OCR ")


backend = st.selectbox("OCR mode (hybrid uses both; choose one to force)", ["Hybrid (Paddle + Easy)", "PaddleOCR only", "EasyOCR only"])
uploaded = st.file_uploader("Upload Aadhaar image or PDF", type=["png", "jpg", "jpeg", "pdf"])

if uploaded:
    st.success("Processing — this may take a few seconds depending on the file size.")
    uploaded.seek(0)
    text, meta = extract_text_from_file(uploaded)
    st.subheader("Merged OCR text (top crops)")
    st.text_area("OCR Output", text, height=300)

    # parse robustly
    name, father, dob, age, debug = robust_parse_aadhar(text)
    st.subheader("Parsed fields (editable)")
    name = st.text_input("Name", value=name)
    father = st.text_input("Father Name", value=father)
    dob = st.text_input("DOB (DD/MM/YYYY)", value=dob)
    age = st.number_input("Age", value=age if age else 0, min_value=0, max_value=120)

    st.write("Parser debug:", debug)
    st.write("OCR crop metadata:", meta)

    if st.button("Save to MySQL"):
        save_record(name, father, dob, int(age))
        st.success("Saved to DB")

st.subheader("Saved records ")
if st.button("Load saved"):
    rows = load_records()
    import pandas as pd
    df = pd.DataFrame(rows, columns=["name", "father_name", "dob", "age"])
    st.dataframe(df)


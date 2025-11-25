import streamlit as st
from PIL import Image
import numpy as np
import easyocr
import re
from datetime import datetime
import sqlite3
import pandas as pd

st.title("Aadhaar OCR Extractor")


conn = sqlite3.connect("aadhaar_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS aadhaar_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    father_name TEXT,
    dob TEXT,
    age INTEGER,
    gender TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ---------------------------
reader = easyocr.Reader(['en'])

uploaded = st.file_uploader("Upload Aadhaar Image", type=["jpg","jpeg","png","pdf"])

if uploaded:
    img = Image.open(uploaded)
    st.image(img, width=320)

    results = reader.readtext(np.array(img))
    lines = [text for (_, text, _) in sorted(results, key=lambda x: x[0][0][1])]

    st.write("### OCR Lines:")
    for i, line in enumerate(lines):
        st.text(f"{i+1}: {line}")

    def clean_line(line):
        return re.sub(r'[^A-Za-z .:-]', '', line).strip()

 
    dob = None
    dob_index = -1
    for i, line in enumerate(lines):
        match = re.search(r'\d{2}[/-]\d{2}[/-]\d{4}', line)
        if match:
            dob = match.group(0)
            dob_index = i
            break

    gender = None
    for line in lines:
        if "FEMALE" in line.upper():
            gender = "Female"
        elif "MALE" in line.upper():
            gender = "Male"

    
    father = None
    father_keywords = ["S/O", "D/O", "C/O", "S/o", "D/o", "C/o", "DIO", "Dio"]

    for line in lines:
        cleaned = re.sub(r'[^A-Za-z0-9 .:/-]', '', line).strip()
        if any(k.lower() in cleaned.lower() for k in father_keywords):
            father = re.sub(
                r'(?i)(S/O|D/O|C/O|S/o|D/o|C/o|DIO|Dio)\s*[:\-]?',
                '',
                cleaned
            ).strip()
            father = re.sub(r'[^A-Za-z .]', '', father).strip()
            break

    if (not father or len(father) < 3) and dob_index > 1:
        for i in range(dob_index - 1, dob_index - 4, -1):
            cl = clean_line(lines[i])
            if 3 <= len(cl) <= 25:
                father = cl
                break

    
    name = None
    if dob_index > 0:
        possible_names = []
        for i in range(dob_index - 1, max(dob_index - 5, -1), -1):
            cl = clean_line(lines[i])
            if cl and not any(x in cl.lower() for x in ["government", "india", "dob", "enrol"]):
                if 3 <= len(cl) <= 30:
                    possible_names.append(cl)

        if possible_names:
            name = possible_names[-2]

  
    age = None
    if dob:
        try:
            d = datetime.strptime(dob, "%d/%m/%Y")
            today = datetime.today()
            age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
        except:
            pass

   
    cursor.execute("""
        INSERT INTO aadhaar_details (name, father_name, dob, age, gender)
        VALUES (?, ?, ?, ?, ?)
    """, (name, father, dob, age, gender))

    conn.commit()

    st.success("Data saved to database successfully!")

    st.write("### Extracted Details:")
    st.write("**Name:**", name)
    st.write("**Father Name:**", father)
    st.write("**DOB:**", dob)
    st.write("**Age:**", age)
    st.write("**Gender:**", gender)

st.write("##View Saved Aadhaar Records")

if st.button("Load Database Records"):
    df = pd.read_sql_query("SELECT * FROM aadhaar_details ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True)



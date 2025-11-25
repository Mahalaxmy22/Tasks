import streamlit as st
import fitz  # PyMuPDF
import mysql.connector
from datetime import datetime, date
import re
from PIL import Image
import pytesseract

# ---------------- MySQL Connection ----------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="maha",
        database="aadhaar_db"
    )

# ---------------- Age Calculation ----------------
def calculate_age(dob):
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

# ---------------- Extract Text from PDF/Image ----------------
def extract_text_from_file(uploaded_file):
    file_type = uploaded_file.type

    if "pdf" in file_type:
        pdf = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        text = ""
        for page in pdf:
            page_text = page.get_text("text")  # Extract digital text
            if page_text.strip():
                text += page_text + "\n"
            else:
                # Optional OCR fallback
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text += pytesseract.image_to_string(img, lang='eng') + "\n"
        return text

    elif "image" in file_type:
        img = Image.open(uploaded_file)
        return pytesseract.image_to_string(img, lang='eng')

    else:
        return "Unsupported file type!"

# ---------------- Parse Aadhaar Details ----------------
def parse_aadhar_data(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    name, father, dob, age = "", "", "", 0
    after_enrolment = False

    for line in lines:
        # Check for Enrolment No
        if re.search(r'Enrolment No', line, re.IGNORECASE):
            after_enrolment = True
            continue

        # Extract Name: first valid line after Enrolment No
        if after_enrolment and not name:
            if re.match(r'^[Tt][Oo]$', line) or re.search(r'X{2,}', line):
                continue
            candidate = re.sub(r'[^A-Za-z ]', '', line).strip()
            if len(candidate) >= 2:
                name = candidate
                after_enrolment = False
                continue

        # Father Name
        father_match = re.search(r'(D/O|S/O)[:\s]*([A-Za-z ]+)', line, re.IGNORECASE)
        if father_match:
            father = re.sub(r'[^A-Za-z ]', '', father_match.group(2)).strip()

        # DOB
        dob_match = re.search(r'DOB[:\s]*(\d{2}/\d{2}/\d{4})', line, re.IGNORECASE)
        if dob_match:
            dob = dob_match.group(1)
            try:
                dob_dt = datetime.strptime(dob, "%d/%m/%Y").date()
                age = calculate_age(dob_dt)
            except:
                age = 0

    return name, father, dob, age

# ---------------- Insert Into MySQL ----------------
def insert_into_db(name, father, dob, age):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Convert DOB to MySQL format YYYY-MM-DD
    dob_mysql = None
    if dob:
        try:
            dob_dt = datetime.strptime(dob, "%d/%m/%Y").date()
            dob_mysql = dob_dt.strftime("%Y-%m-%d")
        except:
            dob_mysql = None

    sql = """
        INSERT INTO aadhar_data (name, father_name, dob, age)
        VALUES (%s, %s, %s, %s)
    """
    cursor.execute(sql, (name, father, dob_mysql, age))
    conn.commit()
    conn.close()

# ---------------- Fetch All ----------------
def fetch_all_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, father_name, dob, age FROM aadhar_data")
    rows = cursor.fetchall()
    conn.close()
    return rows

# ---------------- Streamlit UI ----------------
st.title("Aadhaar OCR Reader & Database Saver")

tab1, tab2 = st.tabs(["Upload Aadhaar", "View Uploaded Data"])

# ------------ TAB 1 ------------
with tab1:
    st.header("Upload Aadhaar Document")
    uploaded_file = st.file_uploader("Upload Image or PDF", type=["png", "jpg", "jpeg", "pdf"])

    if uploaded_file:
        st.success("File uploaded successfully!")
        text = extract_text_from_file(uploaded_file)
        st.text_area("Extracted Text", text, height=200)

        name, father, dob, age = parse_aadhar_data(text)

        # Editable Form
        st.subheader("Extracted Details (Editable)")
        name = st.text_input("Name", value=name)
        father = st.text_input("Father Name", value=father)
        dob = st.text_input("DOB (DD/MM/YYYY)", value=dob)
        age = st.number_input("Age", value=age if age else 0)

        if st.button("Save to Database"):
            insert_into_db(name, father, dob, age)
            st.success("Data saved successfully!")

# ------------ TAB 2 ------------
with tab2:
    st.header("Saved Aadhaar Records")
    data = fetch_all_data()
    if data:
        st.dataframe(
            {
                "Name": [row[0] for row in data],
                "Father Name": [row[1] for row in data],
                "DOB": [row[2] for row in data],
                "Age": [row[3] for row in data],
            }
        )
    else:
        st.info("No records found yet.")

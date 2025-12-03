from flask import Flask, jsonify, request
import mysql.connector
from datetime import datetime

app = Flask(__name__)

def get_connection():
    return mysql.connector.connect(
        host="muthoot-dev.cjy8www4slml.eu-north-1.rds.amazonaws.com",
        user="muthoot_user",
        password="bXV0aG9vdEAxMjM",
        database="muthoot_dev"
    )

def get_value(sql, params=None):
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params or ())
        row = cursor.fetchone()
        return float(row[0]) if row and row[0] is not None else 0
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def format_seconds(seconds):
    if seconds < 60:
        clean = round(seconds, 1)
        if float(clean).is_integer():
            clean = int(clean)
        return f"{clean} seconds"

    minutes = seconds / 60
    clean = round(minutes, 1)
    if float(clean).is_integer():
        clean = int(clean)
    return f"{clean} min"


@app.route("/api/kpis", methods=["GET"])
def api_kpis():
    date_input = request.args.get("date")

    if not date_input:
        return jsonify({"error": "Use /api/kpis?date=YYYY-MM-DD OR curdate"}), 400

    if date_input.lower() == "curdate":
        files = get_value("""
            SELECT SUM(is_doc_processed='y')
            FROM file_metadata
            WHERE DATE(time_stamp)=CURDATE();
        """)
        pages = get_value("""
            SELECT SUM(texteract_pages)
            FROM file_metadata
            WHERE DATE(time_stamp)=CURDATE()
              AND texteract_pages IS NOT NULL;
        """)
        avg_time = get_value("""
            SELECT AVG(TIMESTAMPDIFF(SECOND, process_start_time, process_end_time))
            FROM file_metadata
            WHERE DATE(process_end_time)=CURDATE();
        """)

        return jsonify({
            "date": "curdate",
            "files_processed": str(int(files)),
            "texteract_pages": str(int(pages)),
            "avg_processing_time": format_seconds(avg_time)
        })

    try:
        datetime.strptime(date_input, "%Y-%m-%d")
    except:
        return jsonify({"error": "Date must be YYYY-MM-DD"}), 400

    files = get_value("""
        SELECT SUM(is_doc_processed='y')
        FROM file_metadata
        WHERE DATE(time_stamp)=%s;
    """, (date_input,))

    pages = get_value("""
        SELECT SUM(texteract_pages)
        FROM file_metadata
        WHERE DATE(time_stamp)=%s
          AND texteract_pages IS NOT NULL;
    """, (date_input,))

    avg_time = get_value("""
        SELECT AVG(TIMESTAMPDIFF(SECOND, process_start_time, process_end_time))
        FROM file_metadata
        WHERE DATE(process_end_time)=%s;
    """, (date_input,))

    return jsonify({
        "date": date_input,
        "files_processed": str(int(files)),
        "texteract_pages": str(int(pages)),
        "avg_processing_time": format_seconds(avg_time)
    })

if __name__ == "__main__":
    app.run(debug=True)

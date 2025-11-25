OCR- Optical Character Recognition

This project uses EasyOCR to extract text from Aadhaar images (JPG/PNG).
The uploaded image is processed to detect text line by line in English.
It identifies key fields like Name, Father Name, and DOB using regex and heuristics.
The extracted DOB is used to calculate the Age automatically.
All details are saved into a SQLite database for easy viewing and export.
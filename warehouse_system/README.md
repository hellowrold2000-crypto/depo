# Warehouse Intelligence

Run:
1. python -m venv .venv
2. .venv\Scripts\activate  (Windows) or source .venv/bin/activate
3. pip install -r requirements.txt
4. python app.py
5. Open http://127.0.0.1:5000

Input columns accepted (Kurdish/English aliases): code, qty, color, year, store, size.
The engine supports XLSX, XLS and CSV.

Rules:
- General families use a configurable stock threshold (default 10).
- GM/GMSN, PN-family and TTS/TSS/TS are size-sensitive; default threshold is 3 per model/color/year/size/store.
- Transfers prefer the same province. Cross-province fallback is optional and disabled by default.
- If no suitable donor exists, the missing quantity is assigned to DEPO.
- A separate Excel workbook is produced with Inventory Analysis, Transfers and Stores sheets.

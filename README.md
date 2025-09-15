
python -m venv lamptest && lamptest\Scripts\activate
pip install -r requirements.txt

@dmin123

## QR setting
^XA
^MD10                     ; 🔥 Max burn intensity (0–30, 10+ is good)
^PR2                      ; 🐢 Slower print speed = darker
^CI28                     ; 🔤 UTF-8 encoding (optional, safe)
^PW200                    ; ↔ Label width (adjust as per paper)
^LL120                    ; ↕ Label length
^FO30,10^BQN,2,4          ; 📐 Model 2, magnification 4 (≈10x10mm)
^FDLA,{qr_data}^FS        ; 📄 QR data
^XZ
"""

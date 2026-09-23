from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import pandas as pd
import numpy as np
import re, os, uuid, unicodedata
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "warehouse-system-secret-change-me"
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

STORES = {
    "DP 001": ("Erbil", "Majidi mall santoria"),
    "DP 002": ("Erbil", "Family mall bisse"),
    "DP 006": ("Erbil", "Majidi mall outlet"),
    "DP 010": ("Erbil", "Family mall santoria"),
    "DP 011": ("Suleymaniye", "Majidi mall santoria"),
    "DP 012": ("Duhok", "Family mall santoria"),
    "DP 013": ("Baghdad", "Mall santoria"),
    "DP 014": ("Erbil", "Dream mall santoria"),
    "DP 015": ("Baghdad", "Zyoona mall santoria"),
    "DP 016": ("Erbil", "Gulan mall santoria"),
    "DP 017": ("Suleymaniye", "Family mall santoria"),
    "DP 018": ("Erbil", "Grand Majidi mall santoria"),
    "DP 019": ("Erbil", "Ankawa street santoria"),
    "DP 021": ("Baghdad", "Almansour mall santoria"),
    "DP 022": ("Kirkuk", "Kerkuk mall santoria"),
    "DP 023": ("Karbala", "Al-harith mall santoria"),
    "DP 024": ("Baghdad", "Jadreya mall santoria"),
    "DP 025": ("Basra", "Time square mall santoria"),
    "DP 026": ("Suleymaniye", "Cadde Asti santoria"),
    "DP 027": ("Baghdad", "Iraq mall santoria"),
    "DP 028": ("Suleymaniye", "Shorsh street santoria"),
    "DP 029": ("Najaf", "Firat mall santoria"),
    "DP 030": ("Baghdad", "Cadde Arasat santoria"),
    "DP 031": ("Duhok", "Kro santoria"),
}

# Explicit code families supplied by the user.
SPECIAL_PREFIXES = (
    "GM", "GMSN", "PNJ", "PNSN", "PNKT", "PNJSN", "PN",
    "TTS", "TSS", "TS",
)
# More specific prefixes must be checked before shorter prefixes.
CODE_FAMILIES = [
    ("TKSN", "Suit (TKSN/TK)"),
    ("TK", "Suit (TKSN/TK)"),
    ("TTS", "T-Shirt (TTS/TSS/TS)"),
    ("TSS", "T-Shirt (TTS/TSS/TS)"),
    ("TS", "T-Shirt (TTS/TSS/TS)"),
    ("MNSN", "Undershirt (MNSN/PDSN/PD)"),
    ("PDSN", "Undershirt (MNSN/PDSN/PD)"),
    ("PD", "Undershirt (MNSN/PDSN/PD)"),
    ("GMSN", "Shirt (GM/GMSN)"),
    ("GM", "Shirt (GM/GMSN)"),
    ("PNJSN", "Pants (PNJ/PNSN/PNKT/PNJSN/PN)"),
    ("PNSN", "Pants (PNJ/PNSN/PNKT/PNJSN/PN)"),
    ("PNKT", "Pants (PNJ/PNSN/PNKT/PNJSN/PN)"),
    ("PNJ", "Pants (PNJ/PNSN/PNKT/PN)"),
    ("PN", "Pants (PNJ/PNSN/PNKT/PN)"),
    ("AYAK", "Shoes (AY/AYAK/AYSN)"),
    ("AYSN", "Shoes (AY/AYAK/AYSN)"),
    ("AY", "Shoes (AY/AYAK/AYSN)"),
]

HEADER_ALIASES = {
    "code": ["code","کۆد","کود","model","sku","itemcode","item code","productcode"],
    "qty": ["qty","quantity","عدد","بڕ","count","stock","quantity available"],
    "color": ["color","ڕەنگ","رەنگ","رنگ","colour"],
    "year": ["year","ساڵ","سال"],
    "store": ["store","دوکان","دوکان","dp","branch","shop","location"],
    "size": ["size","قەبارە","قياس","قیاس","سایز"],
}

def norm_text(x):
    if pd.isna(x): return ""
    s = str(x).strip()
    s = s.replace("ي","ی").replace("ى","ی").replace("ك","ک")
    s = re.sub(r"\s+", " ", s)
    return s

def norm_key(x):
    s = norm_text(x).lower()
    s = re.sub(r"[_\-/]+", " ", s)
    s = re.sub(r"[^a-z0-9\u0600-\u06ff ]+", "", s)
    return re.sub(r"\s+", " ", s).strip()

def arabic_digits_to_latin(s):
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return str(s).translate(trans)

def parse_qty(x):
    if pd.isna(x): return 0.0
    s = arabic_digits_to_latin(str(x)).replace(",", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else 0.0

def clean_store(x):
    s = norm_text(x).upper()
    m = re.search(r"DP\s*0*(\d+)", s)
    if m:
        return f"DP {int(m.group(1)):03d}"
    return norm_text(x)

def find_column(columns, aliases):
    normalized = {norm_key(c): c for c in columns}
    for alias in aliases:
        a = norm_key(alias)
        if a in normalized:
            return normalized[a]
    # fuzzy fallback
    for c in columns:
        nc = norm_key(c)
        if any(norm_key(a) in nc or nc in norm_key(a) for a in aliases):
            return c
    return None

def detect_columns(df):
    cols = list(df.columns)
    result = {}
    missing = []
    for key, aliases in HEADER_ALIASES.items():
        result[key] = find_column(cols, aliases)
        if key in ("code","qty","color","store") and not result[key]:
            missing.append(key)
    return result, missing

def classify(code):
    c = re.sub(r"[^A-Z0-9]", "", norm_text(code).upper())
    for prefix, family in CODE_FAMILIES:
        if c.startswith(prefix):
            return family
    return "Other / Unclassified"

def is_special(code):
    c = re.sub(r"[^A-Z0-9]", "", norm_text(code).upper())
    return any(c.startswith(p) for p in SPECIAL_PREFIXES)

def read_excel(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    if ext == ".xls":
        return pd.read_excel(path, engine="xlrd")
    return pd.read_excel(path, engine="openpyxl")

def store_province(store):
    return STORES.get(clean_store(store), ("Unknown", ""))[0]

def store_name(store):
    s=clean_store(store)
    return STORES.get(s, ("Unknown",""))[1]

def build_analysis(df, general_threshold=10, special_threshold=3, allow_cross_region_fallback=True):
    rows=[]
    for _, r in df.iterrows():
        code=norm_text(r["code"]); color=norm_text(r["color"]); year=norm_text(r.get("year",""))
        store=clean_store(r["store"]); size=norm_text(r.get("size",""))
        qty=parse_qty(r["qty"]); family=classify(code); special=is_special(code)
        rows.append({
            "code":code,"color":color,"year":year,"size":size,"store":store,
            "qty":qty,"family":family,"special":special,
            "province":store_province(store),"store_name":store_name(store)
        })
    data=pd.DataFrame(rows)
    if data.empty:
        return pd.DataFrame(), pd.DataFrame()

    # For size-sensitive families, inventory is balanced by model + color + year + size + store.
    # For other families, it is balanced by model + color + year + store.
    key_cols_special=["code","color","year","size","store"]
    key_cols_general=["code","color","year","store"]
    special_data=data[data["special"]].groupby(key_cols_special, dropna=False, as_index=False)["qty"].sum()
    general_data=data[~data["special"]].groupby(key_cols_general, dropna=False, as_index=False)["qty"].sum()
    if "size" not in general_data: general_data["size"]=""

    combined=pd.concat([special_data.assign(special=True), general_data.assign(special=False)], ignore_index=True)
    combined["family"]=combined["code"].map(classify)
    combined["province"]=combined["store"].map(store_province)
    combined["store_name"]=combined["store"].map(store_name)
    combined["threshold"]=np.where(combined["special"], special_threshold, general_threshold)

    # Status:
    # healthy >= threshold; shortage < threshold; zero = critical.
    combined["status"]=np.select(
        [combined["qty"]<=0, combined["qty"]<combined["threshold"], combined["qty"]>=combined["threshold"]],
        ["CRITICAL / EMPTY","SHORTAGE","HEALTHY"],
        default="HEALTHY"
    )

    transfers=[]
    # Match shortage to surplus within the same item identity.
    identity=["code","color","year"]
    for _, need in combined[combined["qty"] < combined["threshold"]].sort_values(["qty"]).iterrows():
        remaining=max(0, need["threshold"]-need["qty"])
        if remaining <= 0: continue

        # Same size for special families. General families can transfer model/color/year.
        mask=(combined["code"]==need["code"])&(combined["color"]==need["color"])&(combined["year"]==need["year"])&(combined["qty"]>combined["threshold"])
        if need["special"]:
            mask &= combined["size"].astype(str)==str(need["size"])
        candidates=combined[mask].copy()
        if candidates.empty:
            continue

        # First use same province, then other provinces only if fallback is enabled.
        candidates["same_province"]=(candidates["province"]==need["province"]).astype(int)
        candidates["distance_rank"]=np.where(candidates["same_province"]==1,0,1)
        candidates=candidates.sort_values(["distance_rank","qty"], ascending=[True,False])

        for idx, donor in candidates.iterrows():
            if remaining<=0: break
            surplus=max(0, donor["qty"]-donor["threshold"])
            if surplus<=0: continue
            # Cross-region transfers are permitted only as an emergency fallback.
            same_region=donor["province"]==need["province"]
            if not same_region and not allow_cross_region_fallback:
                continue
            amount=min(remaining,surplus)
            transfers.append({
                "code":need["code"],"family":need["family"],"color":need["color"],"year":need["year"],
                "size":need["size"],"from_store":donor["store"],"from_store_name":donor["store_name"],
                "from_province":donor["province"],"to_store":need["store"],"to_store_name":need["store_name"],
                "to_province":need["province"],"qty":int(amount),
                "reason":"Same province" if same_region else "EMERGENCY / cross-province fallback"
            })
            remaining-=amount

        if remaining>0:
            transfers.append({
                "code":need["code"],"family":need["family"],"color":need["color"],"year":need["year"],
                "size":need["size"],"from_store":"DEPO","from_store_name":"DEPO / Central Warehouse",
                "from_province":"CENTRAL","to_store":need["store"],"to_store_name":need["store_name"],
                "to_province":need["province"],"qty":int(remaining),
                "reason":"No suitable store surplus → DEPO"
            })

    transfer_df=pd.DataFrame(transfers)

    # If a store has exactly 3 in a special size, flag it for review without automatically moving it.
    combined["review_note"]=""
    exact_three=combined["special"] & (combined["qty"]==3)
    combined.loc[exact_three,"review_note"]="REVIEW: exactly 3 in this size/color — keep unless manager decides to rebalance."

    return combined, transfer_df

@app.route("/", methods=["GET","POST"])
def index():
    if request.method=="POST":
        f=request.files.get("file")
        if not f or not f.filename:
            flash("تکایە فایلێک هەڵبژێرە.")
            return redirect(url_for("index"))
        ext=os.path.splitext(f.filename)[1].lower()
        if ext not in (".xlsx",".xls",".csv"):
            flash("تەنها XLSX, XLS یان CSV پشتگیری دەکرێت.")
            return redirect(url_for("index"))
        token=uuid.uuid4().hex
        path=os.path.join(UPLOAD_DIR, token+"_"+secure_filename(f.filename))
        f.save(path)
        try:
            df=read_excel(path)
            mapping,missing=detect_columns(df)
            if missing:
                flash("کۆلۆمی پێویست نەدۆزرایەوە: "+", ".join(missing))
                return redirect(url_for("index"))
            clean=pd.DataFrame({
                "code":df[mapping["code"]],
                "qty":df[mapping["qty"]],
                "color":df[mapping["color"]],
                "year":df[mapping["year"]] if mapping["year"] else "",
                "store":df[mapping["store"]],
                "size":df[mapping["size"]] if mapping["size"] else "",
            })
            # remove blank rows
            clean=clean[clean["code"].notna() & clean["store"].notna()].copy()
            a,t=build_analysis(clean,
                general_threshold=int(request.form.get("general_threshold",10)),
                special_threshold=int(request.form.get("special_threshold",3)),
                allow_cross_region_fallback=request.form.get("cross_fallback")=="on")
            result_path=os.path.join(UPLOAD_DIR, token+"_result.xlsx")
            with pd.ExcelWriter(result_path, engine="openpyxl") as writer:
                a.to_excel(writer,index=False,sheet_name="Inventory Analysis")
                t.to_excel(writer,index=False,sheet_name="Transfers")
                pd.DataFrame(list(STORES.items()),columns=["Store","Province_and_Name"]).to_excel(writer,index=False,sheet_name="Stores")
            summary={
                "rows":len(clean),"items":a["code"].nunique() if not a.empty else 0,
                "shortages":int((a["status"]=="SHORTAGE").sum()) if not a.empty else 0,
                "critical":int((a["status"]=="CRITICAL / EMPTY").sum()) if not a.empty else 0,
                "transfers":len(t),
                "transfer_qty":int(t["qty"].sum()) if not t.empty else 0,
                "depo":int((t["from_store"]=="DEPO").sum()) if not t.empty else 0,
            }
            return render_template("result.html", summary=summary, analysis=a.to_dict("records"), transfers=t.to_dict("records"), token=token)
        except Exception as e:
            flash("هەڵە لە خوێندنەوە/شیکردنەوەی فایل: "+str(e))
            return redirect(url_for("index"))
    return render_template("index.html", stores=STORES)

@app.route("/download/<token>")
def download(token):
    path=os.path.join(UPLOAD_DIR, token+"_result.xlsx")
    if not os.path.exists(path):
        return "File not found",404
    return send_file(path,as_attachment=True,download_name="warehouse_optimization_result.xlsx")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)

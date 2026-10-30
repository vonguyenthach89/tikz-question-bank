import os
import hashlib
import subprocess
import json
import gspread

GITHUB_USER = "vonguyenthach"  # Thay bằng username GitHub của thầy
GITHUB_REPO = "tikz-question-bank"
BRANCH = "main"

SPREADSHEET_KEY = "1Yqo9L3cgyliMA4sS_X2-U8kU1fkc1GYfJux8TT1vmy0"
SHEET_NAME = "NganHangCauHoi"  # Tên Tab chứa ngân hàng câu hỏi

OUTPUT_DIR = "images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_string_md5(text: str) -> str:
    return hashlib.md5(text.strip().encode('utf-8')).hexdigest()

def compile_tikz_to_svg(tikz_code: str, hash_md5: str) -> bool:
    output_svg_path = os.path.join(OUTPUT_DIR, f"{hash_md5}.svg")
    
    # Nếu file SVG đã tồn tại trên GitHub thì bỏ qua để tiết kiệm thời gian
    if os.path.exists(output_svg_path):
        return True

    print(f"🔨 Đang biên dịch TikZ mới [MD5: {hash_md5}] ...")
    temp_tex = os.path.join(OUTPUT_DIR, f"temp_{hash_md5}.tex")
    
    full_tex = f"""\\documentclass[tikz, border=2pt]{{standalone}}
\\usepackage[utf8]{{vietnam}}
\\usepackage{{tikz, tkz-tab, pgfplots}}
\\pgfplotsset{{compat=1.18}}
\\begin{{document}}
{tikz_code}
\\end{{document}}"""

    with open(temp_tex, "w", encoding="utf-8") as f:
        f.write(full_tex)

    try:
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={OUTPUT_DIR}", temp_tex], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        temp_pdf = os.path.join(OUTPUT_DIR, f"temp_{hash_md5}.pdf")
        subprocess.run(["dvisvgm", "--pdf", "--font-format=woff2", "--zoom=-1", temp_pdf, "-o", output_svg_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        print(f"✅ Biên dịch thành công: {output_svg_path}")
        return True
    except Exception as e:
        print(f"❌ Lỗi biên dịch: {e}")
        return False
    finally:
        for ext in [".tex", ".pdf", ".aux", ".log"]:
            f_temp = os.path.join(OUTPUT_DIR, f"temp_{hash_md5}{ext}")
            if os.path.exists(f_temp):
                os.remove(f_temp)

def process_tikz_from_sheet():
    sa_key_env = os.getenv("GCP_SA_KEY")
    if not sa_key_env:
        print("⚠️ Không tìm thấy biến môi trường GCP_SA_KEY.")
        return

    creds_dict = json.loads(sa_key_env)
    gc = gspread.service_account_from_dict(creds_dict)
    sh = gc.open_by_key(SPREADSHEET_KEY)
    worksheet = sh.worksheet(SHEET_NAME)

    records = worksheet.get_all_records()

    for row in records:
        # Đọc mã TikZ từ Cột J (tên cột trên Sheet là MaTikZ)
        tikz_code = str(row.get("MaTikZ", "")).strip()
        if tikz_code:
            hash_md5 = get_string_md5(tikz_code)
            compile_tikz_to_svg(tikz_code, hash_md5)

if __name__ == "__main__":
    process_tikz_from_sheet()

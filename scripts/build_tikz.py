import os
import sys
import json
import hashlib
import re
import time
from google.oauth2.service_account import Credentials
import gspread

SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY", "")
OUTPUT_DIR = "images"

import subprocess
import tempfile

def compile_tikz_to_svg(tikz_code):
    """
    Biên dịch mã TikZ thực tế thành SVG bằng pdflatex và dvisvgm trên Ubuntu runner.
    """
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Tạo mã hash MD5 cố định từ mã TikZ
        tikz_hash = hashlib.md5(tikz_code.encode('utf-8')).hexdigest()
        svg_filename = f"{tikz_hash}.svg"
        svg_path = os.path.join(OUTPUT_DIR, svg_filename)
        
        # Nếu file SVG đã biên dịch trước đó, dùng luôn
        if os.path.exists(svg_path):
            github_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
            github_repo = os.environ.get("GITHUB_REPOSITORY_NAME", "")
            cdn_url = f"https://cdn.jsdelivr.net/gh/{github_owner}/{github_repo}@main/{OUTPUT_DIR}/{svg_filename}"
            return cdn_url, svg_filename

        # Đã escape tất cả ngoặc nhọn LaTeX thành {{ và }} để tránh lỗi Python f-string
        latex_content = f"""\\documentclass[tikz,border=2pt]{{standalone}}
\\usepackage{{amsmath,amssymb}}
\\usepackage{{tikz}}
\\usepackage{{tkz-tab}}
\\usepackage{{tkz-euclide}}
\\usetikzlibrary{{shapes.geometric,calc,arrows,arrows.meta,intersections,angles,quotes}}
\\begin{{document}}
{tikz_code}
\\end{{document}}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = os.path.join(tmpdir, "figure.tex")
            with open(tex_file, "w", encoding="utf-8") as f:
                f.write(latex_content)
                
            # 1. Chạy pdflatex biên dịch file LaTeX
            subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "figure.tex"],
                cwd=tmpdir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            
            # 2. Dùng dvisvgm chuyển đổi file PDF thành SVG
            subprocess.run(
                ["dvisvgm", "--pdf", "figure.pdf", "-o", svg_path],
                cwd=tmpdir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )

        # Lấy link CDN jsDelivr
        github_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
        github_repo = os.environ.get("GITHUB_REPOSITORY_NAME", "")
        cdn_url = f"https://cdn.jsdelivr.net/gh/{github_owner}/{github_repo}@main/{OUTPUT_DIR}/{svg_filename}"
        
        return cdn_url, svg_filename
        
    except Exception as e:
        print(f"⚠️ Lỗi biên dịch LaTeX/TikZ thực tế: {str(e)}")
        return None, None

def process_tikz_from_sheet():
    print("🚀 Bắt đầu quá trình quét và xử lý TikZ từ cột Mã TikZ (Cột J)...")
    
    sa_key_json = os.environ.get("GCP_SA_KEY")
    if not sa_key_json:
        raise ValueError("❌ Không tìm thấy biến môi trường GCP_SA_KEY!")

    service_account_info = json.loads(sa_key_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(credentials)

    sh = gc.open_by_key(SPREADSHEET_KEY)
    worksheet = sh.worksheet("NganHangCauHoi")
    print(f"📂 Đã mở Sheet: {worksheet.title}")

    rows = worksheet.get_all_values()
    print(f"📊 Tổng số dòng đọc được từ Google Sheet: {len(rows)}")
    
    if len(rows) <= 1:
        print("⚠️ Sheet hiện không có dữ liệu câu hỏi nào.")
        return

    updated_count = 0
    for row_idx in range(1, len(rows)):
        row = rows[row_idx]
        row_num = row_idx + 1 # Dòng thực tế trên Sheet
        
        # Đảm bảo dòng có đủ cột (Cột J tương ứng với index 9)
        if len(row) < 10:
            continue
            
        id_val = row[1] if len(row) > 1 and row[1] else "0"
        noi_dung = row[2] if len(row) > 2 else ""
        ma_tikz_val = row[9] if len(row) > 9 else "" # Cột J: MaTikz
        
        # Tạo Mã định danh: lấy số đầu của ID kết hợp với số dòng
        first_char_id = id_val[0] if id_val else "X"
        ma_dinh_danh = f"{first_char_id}{row_num}"
        
        # Nếu cột J (MaTikz) có chứa mã TikZ
        if ma_tikz_val and("\\begin{tikzpicture}" in ma_tikz_val):
            print(f"🔍 Phát hiện mã TikZ tại cột J của dòng {row_num} (Mã định danh: {ma_dinh_danh})")
            
            cdn_url, svg_filename = compile_tikz_to_svg(ma_tikz_val)
            if cdn_url:
                # Tạo thẻ ảnh SVG CDN
                img_tag = f'<img src="{cdn_url}" alt="TikZ Figure" class="img-fluid"/>'
                
                # Nếu nội dung chưa có thẻ ảnh này, ta ghép thêm thẻ ảnh vào nội dung (hoặc thay thế nếu cần)
                if img_tag not in noi_dung:
                    noi_dung = noi_dung + "\n" + img_tag
                
                # Cập nhật lần lượt các cột lên Google Sheet có kèm thời gian nghỉ chống lỗi 429
                worksheet.update_cell(row_num, 1, ma_dinh_danh) # Cột A: MaDinhDanh
                time.sleep(1)
                worksheet.update_cell(row_num, 3, noi_dung)    # Cột C: NoiDung (bổ sung ảnh)
                time.sleep(1)
                # Cột J giữ nguyên hoặc cập nhật lại mã TikZ nếu cần
                
                updated_count += 1

    print(f"🎉 Hoàn thành xử lý! Đã biên dịch và cập nhật thành công {updated_count} câu hỏi từ cột MaTikz.")

if __name__ == "__main__":
    try:
        process_tikz_from_sheet()
    except Exception as e:
        print(f"🔥 LỖI NGHIÊM TRỌNG TRONG SCRIPT PYTHON: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

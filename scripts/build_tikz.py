import os
import sys
import json
import hashlib
import re
import time
import subprocess
import tempfile
from google.oauth2.service_account import Credentials
import gspread

SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY", "")
OUTPUT_DIR = "images"

def compile_tikz_to_svg(tikz_code):
    """
    Biên dịch mã TikZ thực tế thành SVG bằng pdflatex và pdf2svg trên Ubuntu runner.
    """
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Tự động vá lỗi gõ nhầm chính tả \begin{tikpicture} thành \begin{tikzpicture}
        tikz_code = tikz_code.replace("\\begin{tikpicture}", "\\begin{tikzpicture}")
        tikz_code = tikz_code.replace("\\end{tikpicture}", "\\end{tikzpicture}")

        # Tạo mã hash MD5 cố định từ mã TikZ
        tikz_hash = hashlib.md5(tikz_code.encode('utf-8')).hexdigest()
        svg_filename = f"{tikz_hash}.svg"
        svg_path = os.path.join(OUTPUT_DIR, svg_filename)
        
        # Nếu file SVG đã biên dịch trước đó, sử dụng lại
        if os.path.exists(svg_path):
            github_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
            github_repo = os.environ.get("GITHUB_REPOSITORY_NAME", "")
            cdn_url = f"https://cdn.jsdelivr.net/gh/{github_owner}/{github_repo}@main/{OUTPUT_DIR}/{svg_filename}"
            return cdn_url, svg_filename

        # Cấu trúc Template LaTeX chuẩn cho TikZ / tkz-tab / tkz-euclide
        latex_content = f"""\\documentclass[tikz,border=2pt]{{standalone}}
\\usepackage{{amsmath,amssymb}}
\\usepackage{{tikz}}
\\usepackage{{tkz-tab}}
\\usepackage{{tkz-euclide}}
\\usetikzlibrary{{shapes.geometric,calc,arrows,arrows.meta,intersections,angles,quotes,patterns}}
\\begin{{document}}
{tikz_code}
\\end{{document}}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = os.path.join(tmpdir, "figure.tex")
            pdf_file = os.path.join(tmpdir, "figure.pdf")
            log_file = os.path.join(tmpdir, "figure.log")
            
            with open(tex_file, "w", encoding="utf-8") as f:
                f.write(latex_content)
                
            # 1. Chạy pdflatex biên dịch LaTeX sang PDF
            res_pdf = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "figure.tex"],
                cwd=tmpdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if res_pdf.returncode != 0:
                print(f"❌ Lỗi pdflatex khi biên dịch khối TikZ:")
                if os.path.exists(log_file):
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as lf:
                        lines = lf.readlines()
                        err_lines = [line.strip() for line in lines if line.startswith("!")]
                        print("   🔍 Chi tiết lỗi LaTeX:", " | ".join(err_lines[:5]))
                return None, None
            
            # 2. Chuyển đổi từ PDF sang SVG bằng pdf2svg
            res_svg = subprocess.run(
                ["pdf2svg", pdf_file, svg_path],
                cwd=tmpdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if res_svg.returncode != 0:
                print(f"❌ Lỗi pdf2svg: {res_svg.stderr}")
                return None, None

        # Link CDN jsDelivr
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
        
        if len(row) < 10:
            continue
            
        id_val = row[1] if len(row) > 1 and row[1] else "0"
        noi_dung = row[2] if len(row) > 2 else ""
        ma_tikz_val = row[9] if len(row) > 9 else "" # Cột J: MaTikz
        
        # Chuẩn hóa kiểm tra mã TikZ (chấp nhận cả tikpicture nếu gõ nhầm)
        if ma_tikz_val and ("\\begin{tikzpicture}" in ma_tikz_val or "\\begin{tikpicture}" in ma_tikz_val):
            first_char_id = id_val[0] if id_val else "X"
            ma_dinh_danh = f"{first_char_id}{row_num}"
            
            print(f"🔍 Phát hiện mã TikZ tại cột J của dòng {row_num} (Mã định danh: {ma_dinh_danh})")
            
            cdn_url, svg_filename = compile_tikz_to_svg(ma_tikz_val)
            if cdn_url:
                img_tag = f'<img src="{cdn_url}" alt="TikZ Figure" class="img-fluid"/>'
                
                if img_tag not in noi_dung:
                    noi_dung = noi_dung + "\n" + img_tag
                
                worksheet.update_cell(row_num, 1, ma_dinh_danh) # Cột A: MaDinhDanh
                time.sleep(1)
                worksheet.update_cell(row_num, 3, noi_dung)    # Cột C: NoiDung (chèn thẻ ảnh)
                time.sleep(1)
                
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

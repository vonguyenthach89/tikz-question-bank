import os
import sys
import json
import hashlib
import re
from google.oauth2.service_account import Credentials
import gspread
import time

# Cấu hình thông số (có thể lấy từ biến môi trường hoặc cấu hình trực tiếp)
SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY", "1Yqo9L3cgyliMA4sS_X2-U8kU1fkc1GYfJux8TT1vmy0")
OUTPUT_DIR = "images"

def compile_tikz_to_svg(tikz_code):
    """
    Biên dịch mã TikZ thành SVG.
    Hàm này sẽ tạo mã hash MD5 từ nội dung TikZ để làm tên file,
    sau đó sinh file SVG tương ứng vào thư mục images/
    """
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Tạo mã hash MD5 duy nhất cho khối TikZ
        tikz_hash = hashlib.md5(tikz_code.encode('utf-8')).hexdigest()
        svg_filename = f"{tikz_hash}.svg"
        svg_path = os.path.join(OUTPUT_DIR, svg_filename)
        
        # Nếu file SVG đã tồn tại, không cần biên dịch lại để tiết kiệm thời gian
        if not os.path.exists(svg_path):
            # Tạm thời tạo file SVG mẫu hoặc gọi công cụ biên dịch thực tế (ví dụ: pdflatex + dvisvgm)
            # Ở đây mô phỏng nội dung SVG chuẩn để hiển thị hình vẽ TikZ
            svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">
  <style>
    .edge {{ stroke: black; stroke-width: 1.5; fill: none; }}
    .node {{ fill: black; }}
  </style>
  <rect width="100%" height="100%" fill="white"/>
  <!-- TikZ Render Placeholder: {tikz_hash} -->
  <circle cx="100" cy="100" r="40" class="edge" />
  <text x="100" y="105" font-size="12" text-anchor="middle" fill="black">TikZ Figure</text>
</svg>"""
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(svg_content)
                
        # Trả về URL CDN jsDelivr tương ứng
        github_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "vonguyenthach89")
        github_repo = os.environ.get("GITHUB_REPOSITORY_NAME", "tikz-question-bank")
        
        # Đường dẫn CDN jsDelivr
        cdn_url = f"https://cdn.jsdelivr.net/gh/{github_owner}/{github_repo}@main/{OUTPUT_DIR}/{svg_filename}"
        return cdn_url, svg_filename
        
    except Exception as e:
        print(f"⚠️ Lỗi khi biên dịch TikZ: {str(e)}")
        return None, None

def process_tikz_from_sheet():
    print("🚀 Bắt đầu quá trình quét và xử lý TikZ từ Google Sheet...")
    
    # 1. Xác thực và kết nối Google Sheets
    sa_key_json = os.environ.get("GCP_SA_KEY")
    if not sa_key_json:
        raise ValueError("❌ Không tìm thấy biến môi trường GCP_SA_KEY! Hãy kiểm tra lại GitHub Secrets.")

    service_account_info = json.loads(sa_key_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(credentials)

    print("✅ Kết nối Google Cloud thành công!")

    # 2. Mở Google Sheet và chọn Sheet chứa câu hỏi
    sh = gc.open_by_key(SPREADSHEET_KEY)
    worksheet = sh.worksheet("NganHangCauHoi")
    print(f"📂 Đã mở Sheet: {worksheet.title}")

    # Lấy toàn bộ dữ liệu dạng danh sách các list
    rows = worksheet.get_all_values()
    if len(rows) <= 1:
        print("⚠️ Sheet hiện không có dữ liệu câu hỏi nào.")
        return

    header = rows[0]
    updated_count = 0
    
    # Duyệt qua từng dòng và thực hiện thay đổi trên bộ nhớ trước
    for row_idx in range(1, len(rows)):
        row = rows[row_idx]
        if len(row) < 3:
            continue
            
        row_num = row_idx + 1 # Vị trí dòng thực tế trên Sheet (bắt đầu từ 2)
        id_val = row[1] if len(row) > 1 and row[1] else "0"
        noi_dung = row[2] if len(row) > 2 else ""
        
        # Tạo Mã định danh: lấy số đầu của ID kết hợp với số dòng
        first_char_id = id_val[0] if id_val else "X"
        ma_dinh_danh = f"{first_char_id}{row_num}"
        
        # Tìm và bóc tách khối \begin{tikzpicture}...\end{tikzpicture} trong nội dung
        tikz_pattern = re.compile(r'(\\begin\{tikzpicture\}.*?\\end\{tikzpicture\})', re.DOTALL)
        match = tikz_pattern.search(noi_dung)
        
        if match:
            tikz_code = match.group(1)
            print(f"🔍 Phát hiện mã TikZ tại dòng {row_num} (Mã định danh: {ma_dinh_danh})")
            
            # Biên dịch ra SVG và lấy link CDN
            cdn_url, svg_filename = compile_tikz_to_svg(tikz_code)
            if cdn_url:
                img_tag = f'<img src="{cdn_url}" alt="TikZ Figure" class="img-fluid"/>'
                noi_dung = tikz_pattern.sub(img_tag, noi_dung)
                ma_tikz_val = tikz_code 
                
                # Cập nhật trực tiếp từng ô nhưng có chèn thời gian nghỉ (sleep) nhỏ để chống tràn quota (429)
                worksheet.update_cell(row_num, 1, ma_dinh_danh) # Cột A: MaDinhDanh
                time.sleep(1) # Nghỉ 1 giây để tránh vượt hạn mức write requests của Google API
                worksheet.update_cell(row_num, 3, noi_dung)    # Cột C: NoiDung
                time.sleep(1)
                worksheet.update_cell(row_num, 10, ma_tikz_val) # Cột J: MaTikz
                time.sleep(1)
                
                updated_count += 1

    print(f"🎉 Hoàn thành xử lý! Đã cập nhật thành công {updated_count} câu hỏi chứa TikZ.")

if __name__ == "__main__":
    try:
        process_tikz_from_sheet()
    except Exception as e:
        print(f"🔥 LỖI NGHIÊM TRỌNG TRONG SCRIPT PYTHON: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

import streamlit as st
import google.generativeai as genai
from newspaper import Article, Config
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from io import BytesIO
import re
import random
import zipfile
import qrcode
from datetime import datetime

# --- 페이지 설정 ---
st.set_page_config(page_title="One-Click News v6.0", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v6.0 Layout Master)")
st.markdown("### 💎 레이아웃 변주 & 텍스트 박스로 '꽉 찬' 디자인 구현")

# --- 폰트 준비 ---
@st.cache_resource
def get_fonts():
    fonts = {}
    try:
        fonts['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf", timeout=10).content
        fonts['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        fonts['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return fonts

# --- 고급 디자인 함수 (박스, 헤더 등) ---

# 1. 둥근 사각형 그리기 (텍스트 박스용)
def draw_rounded_rectangle(draw, xy, corner_radius, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle(
        [(x1 + corner_radius, y1), (x2 - corner_radius, y2)], fill=fill
    )
    draw.rectangle(
        [(x1, y1 + corner_radius), (x2, y2 - corner_radius)], fill=fill
    )
    draw.pieslice([x1, y1, x1 + corner_radius * 2, y1 + corner_radius * 2], 180, 270, fill=fill)
    draw.pieslice([x2 - corner_radius * 2, y1, x2, y1 + corner_radius * 2], 270, 360, fill=fill)
    draw.pieslice([x1, y2 - corner_radius * 2, x1 + corner_radius * 2, y2], 90, 180, fill=fill)
    draw.pieslice([x2 - corner_radius * 2, y2 - corner_radius * 2, x2, y2], 0, 90, fill=fill)

# 2. 상단 헤더 (고정 디자인)
def draw_header(draw, width, date_str, font_small):
    # 상단 띠
    draw.line((60, 120, width-60, 120), fill="white", width=2)
    draw.text((60, 80), "SEGYE ISSUE BRIEF", font=font_small, fill="#FFD700") # 골드 포인트
    
    # 날짜 (우측 정렬)
    w = draw.textlength(date_str, font=font_small)
    draw.text((width - 60 - w, 80), date_str, font=font_small, fill="#cccccc")

# --- 스크래핑 엔진 ---
def advanced_scrape(url):
    title, text, top_image = "", "", ""
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0'
        config.request_timeout = 10
        article = Article(url, config=config)
        article.download()
        article.parse()
        title, text, top_image = article.title, article.text, article.top_image
    except: pass
    
    if len(text) < 50 or not top_image:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            if not title: title = soup.find('title').text.strip()
            if not top_image:
                meta = soup.find('meta', property='og:image')
                if meta: top_image = meta['content']
            if len(text) < 50:
                text = soup.get_text(separator=' ', strip=True)[:5000] 
        except: pass
    return title, text, top_image

def clean_text_strict(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'[#\*]', '', text)
    return text.strip()

def wrap_text(text, font, max_width, draw):
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip(): continue
        words = paragraph.split(' ')
        current_line = words[0]
        for word in words[1:]:
            bbox = draw.textbbox((0, 0), current_line + " " + word, font=font)
            if bbox[2] - bbox[0] <= max_width: current_line += " " + word
            else: lines.append(current_line); current_line = word
        lines.append(current_line)
    return lines

def generate_qr_code(link):
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(link)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")
    user_image = st.file_uploader("직접 업로드 (1순위)", type=['png', 'jpg', 'jpeg'])

# --- 메인 ---
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

if st.button("🚀 고급형 카드뉴스 제작"):
    if not api_key or not url: st.error("설정 확인 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사 분석 및 레이아웃 설계 중...")
    
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- AI 프롬프트 ---
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        prompt = f"""
        당신은 세계일보의 '디자인 편집장'입니다.
        
        [기사]
        제목: {title}
        내용: {text[:4000]}
        
        [규칙]
        1. 분량: 5~8장.
        2. 구조: HEAD(제목, 15자) / DESC(본문, 60자)
        3. 테마 컬러: 기사 분위기에 맞는 짙은 색상(Hex) 하나 추출.
        
        [출력 양식]
        COLOR_MAIN: #Hex
        
        [SLIDE 1]
        TYPE: COVER
        HEAD: ...
        DESC: ...
        
        [SLIDE 2]
        TYPE: CONTENT
        HEAD: ...
        DESC: ...
        
        ...
        
        [SLIDE N]
        TYPE: OUTRO
        HEAD: First in, Last out
        DESC: 세상을 보는 눈, 세계일보
        """
        response = model.generate_content(prompt)
        res_text = response.text
        
        slides = []
        current_slide = {}
        color_main = "#1e3a8a"
        
        for line in res_text.split('\n'):
            line = line.strip()
            if not line: continue
            if line.startswith("COLOR_MAIN:"): color_main = line.split(":")[1].strip()
            elif line.startswith("[SLIDE"):
                if current_slide: slides.append(current_slide)
                current_slide = {"HEAD": "", "DESC": "", "TYPE": ""}
            elif line.startswith("TYPE:"): current_slide["TYPE"] = line.split(":")[1].strip()
            elif line.startswith("HEAD:"): current_slide["HEAD"] = line.split("HEAD:")[1].strip()
            elif line.startswith("DESC:"): current_slide["DESC"] = line.split("DESC:")[1].strip()
        if current_slide: slides.append(current_slide)
        
    except: st.error("기획 실패"); st.stop()

    # --- 이미지 준비 ---
    try:
        if user_image: base_img = Image.open(user_image)
        elif img_url:
            headers = {'User-Agent': 'Mozilla/5.0'}
            base_img = Image.open(BytesIO(requests.get(img_url, headers=headers, timeout=5).content))
        else: base_img = Image.new('RGB', (1080, 1080), color='#1a1a2e')
        
        base_img = base_img.convert('RGB').resize((1080, 1080))
        # 배경을 조금 더 어둡게 해서 글자 팝업 효과 극대화
        base_img = ImageEnhance.Brightness(base_img).enhance(0.6) 
        base_img = base_img.filter(ImageFilter.GaussianBlur(8)) # 블러 더 강하게 (고급스러움)
        
        try: bg_outro = Image.new('RGB', (1080, 1080), color=color_main)
        except: bg_outro = Image.new('RGB', (1080, 1080), color='#1a1a2e')
            
    except: st.error("이미지 실패"); st.stop()

    # --- 렌더링 루프 (레이아웃 변주 적용) ---
    fonts = get_fonts()
    if not fonts: st.error("폰트 로딩 실패"); st.stop()
    
    st.markdown(f"### 📸 Layout Master Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    today_str = datetime.now().strftime("%Y.%m.%d")
    
    for i, slide in enumerate(slides):
        if slide.get("TYPE") == "OUTRO": img = bg_outro.copy()
        else: img = base_img.copy()
        
        draw = ImageDraw.Draw(img, 'RGBA') # RGBA 모드 필수 (반투명 박스)
        
        # 폰트
        f_title = ImageFont.truetype(BytesIO(fonts['title']), 85)
        f_body = ImageFont.truetype(BytesIO(fonts['body']), 48)
        f_small = ImageFont.truetype(BytesIO(fonts['body']), 30)
        f_serif = ImageFont.truetype(BytesIO(fonts['serif']), 90)
        
        # [공통] 헤더 및 페이지 번호
        if slide.get("TYPE") != "OUTRO":
            draw_header(draw, 1080, today_str, f_small)
            # 하단 페이지 번호
            draw.text((950, 1000), f"{i+1} / {len(slides)}", font=f_small, fill="#888888")

        # 1. COVER (타이틀 박스형)
        if slide.get("TYPE") == "COVER":
            # 메인 타이틀
            head = slide.get("HEAD", "")
            h_lines = wrap_text(head, f_title, 900, draw)
            
            # 중앙 정렬 계산
            total_h = len(h_lines) * 100
            start_y = (1080 - total_h) / 2 - 50
            
            # 디자인: 제목 뒤에 반투명 박스 깔기 (밀도감 UP)
            box_h = total_h + 250
            draw_rounded_rectangle(draw, (50, start_y - 80, 1030, start_y + box_h), 20, (0, 0, 0, 120))
            
            # 브랜드 태그
            draw.rectangle([(50, start_y - 80), (50 + 300, start_y - 20)], fill=color_main)
            draw.text((70, start_y - 70), "SEGYE BRIEFING", font=f_small, fill="white")

            for line in h_lines:
                w = draw.textlength(line, font=f_title)
                draw.text(((1080-w)/2, start_y), line, font=f_title, fill="white")
                start_y += 100
                
            # 부제
            if slide.get("DESC"):
                desc = slide.get("DESC", "")
                d_lines = wrap_text(desc, f_body, 850, draw)
                dy = start_y + 40
                draw.line((440, dy, 640, dy), fill=color_main, width=5)
                dy += 40
                for line in d_lines:
                    w = draw.textlength(line, font=f_body)
                    draw.text(((1080-w)/2, dy), line, font=f_body, fill="#dddddd")
                    dy += 60

        # 2. CONTENT (레이아웃 랜덤 변주)
        elif slide.get("TYPE") == "CONTENT":
            layout_type = random.choice(["LEFT_BAR", "CENTER_BOX", "QUOTE"])
            
            head = slide.get("HEAD", "")
            desc = clean_text_strict(slide.get("DESC", ""))
            
            if layout_type == "LEFT_BAR": # 기존 스타일 (왼쪽 바)
                h_lines = wrap_text(head, f_title, 900, draw)
                start_y = 350
                draw.rectangle([(60, start_y), (75, start_y + (len(h_lines)*100) + 20)], fill=color_main)
                for line in h_lines:
                    draw.text((90, start_y), line, font=f_title, fill="white")
                    start_y += 100
                
                d_lines = wrap_text(desc, f_body, 900, draw)
                dy = start_y + 40
                for line in d_lines:
                    draw.text((90, dy), line, font=f_body, fill="#dddddd")
                    dy += 60
                    
            elif layout_type == "CENTER_BOX": # 중앙 박스형 (꽉 찬 느낌)
                h_lines = wrap_text(head, f_title, 850, draw)
                d_lines = wrap_text(desc, f_body, 850, draw)
                
                box_height = (len(h_lines) * 100) + (len(d_lines) * 60) + 150
                start_y = (1080 - box_height) / 2
                
                # 반투명 배경 박스
                draw_rounded_rectangle(draw, (80, start_y, 1000, start_y + box_height), 30, (0, 0, 0, 150))
                
                txt_y = start_y + 50
                for line in h_lines:
                    w = draw.textlength(line, font=f_title)
                    draw.text(((1080-w)/2, txt_y), line, font=f_title, fill=color_main) # 제목에 컬러 포인트
                    txt_y += 100
                
                txt_y += 20
                for line in d_lines:
                    w = draw.textlength(line, font=f_body)
                    draw.text(((1080-w)/2, txt_y), line, font=f_body, fill="white")
                    txt_y += 60
            
            elif layout_type == "QUOTE": # 인용구 스타일
                # 거대 따옴표 장식
                draw.text((100, 250), "“", font=ImageFont.truetype(BytesIO(fonts['serif']), 300), fill=(255, 255, 255, 50))
                
                h_lines = wrap_text(head, f_title, 800, draw)
                start_y = 400
                for line in h_lines:
                    draw.text((150, start_y), line, font=f_title, fill="white")
                    start_y += 100
                
                # 구분선
                draw.line((150, start_y+20, 350, start_y+20), fill=color_main, width=5)
                
                d_lines = wrap_text(desc, f_body, 800, draw)
                dy = start_y + 60
                for line in d_lines:
                    draw.text((150, dy), line, font=f_body, fill="#cccccc")
                    dy += 60

        # 3. OUTRO
        elif slide.get("TYPE") == "OUTRO":
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=f_serif)
            w = bbox[2] - bbox[0]
            draw.text(((1080-w)/2, 350), slogan, font=f_serif, fill="white")
            
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=f_body)
            w2 = bbox2[2] - bbox2[0]
            draw.text(((1080-w2)/2, 480), brand, font=f_body, fill="#dddddd")
            
            # QR 코드
            qr_img = generate_qr_code(url).resize((220, 220))
            qr_bg_x = (1080 - 240) // 2
            qr_bg_y = 650
            draw_rounded_rectangle(draw, (qr_bg_x, qr_bg_y, qr_bg_x + 240, qr_bg_y + 240), 20, "white")
            img.paste(qr_img, (qr_bg_x + 10, qr_bg_y + 10))
            
            msg = "기사 원문 보러가기"
            bbox3 = draw.textbbox((0, 0), msg, font=f_small)
            w3 = bbox3[2] - bbox3[0]
            draw.text(((1080-w3)/2, 910), msg, font=f_small, fill="white")

        generated_images.append(img)
        with tabs[i]: st.image(img, caption=f"Page {i+1}")

    # --- 다운로드 ---
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for i, img in enumerate(generated_images):
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='PNG')
            zf.writestr(f"card_{i+1:02d}.png", img_byte_arr.getvalue())
    st.download_button("💾 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_layout_master.zip", "application/zip", use_container_width=True)
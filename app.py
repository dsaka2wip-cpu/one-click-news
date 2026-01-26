import streamlit as st
import google.generativeai as genai
from newspaper import Article, Config
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageColor
import io
import random
import zipfile
import qrcode
import os
import numpy as np
import fitz  # PyMuPDF
import re

# --- 페이지 설정 ---
st.set_page_config(page_title="One-Click News v11.0", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v11.0 Intelligence)")
st.markdown("### 💎 빅데이터 시각화(Big Number) & 멀티 포맷 & 컬러 추출 탑재")

# --- [설정] 자산 파일명 ---
ASSET_FILENAMES = {
    "symbol": "segye_symbol.png",
    "text": "segye_text.png",
    "font_title": "Title.ttf",
    "font_body": "Body.ttf",
    "font_serif": "Serif.ttf"
}

# --- 리소스 캐싱 ---
@st.cache_resource
def get_web_resources():
    resources = {}
    try:
        # 제목: 나눔고딕 엑스트라 볼드
        resources['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-ExtraBold.ttf", timeout=10).content
        # 본문: 나눔고딕 볼드
        resources['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        # 명조: 나눔명조 엑스트라 볼드
        resources['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return resources

def load_asset_bytes(uploader, filename, fallback_bytes=None):
    if uploader: return uploader.getvalue()
    if os.path.exists(filename):
        with open(filename, "rb") as f: return f.read()
    return fallback_bytes

def load_logo_image(uploader, filename, width_target):
    data = load_asset_bytes(uploader, filename)
    if not data: return None
    try:
        if filename.lower().endswith('.ai') or (uploader and uploader.name.lower().endswith('.ai')):
            doc = fitz.open(stream=data, filetype="pdf")
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=True)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
        else:
            img = Image.open(io.BytesIO(data)).convert("RGBA")
        ar = img.height / img.width
        return img.resize((width_target, int(width_target * ar)))
    except: return None

# --- [NEW] 이미지에서 메인 색상 추출 ---
def get_dominant_color(pil_img):
    try:
        # 이미지를 P모드(팔레트)로 변환하여 주요 색상 추출
        img = pil_img.copy()
        img = img.convert("P", palette=Image.ADAPTIVE, colors=1)
        palette = img.getpalette()
        # 가장 많이 쓰인 색상 (0번 인덱스)
        color = palette[:3]
        return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
    except:
        return "#FFD700" # 실패 시 골드

# --- 모델 자동 탐색 ---
def get_available_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priorities = ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-1.0-pro", "models/gemini-pro"]
        for p in priorities:
            for m in models:
                if p in m: return m
        return models[0] if models else "models/gemini-pro"
    except: return "models/gemini-pro"

# --- 디자인 유틸리티 ---
def clean_text_spacing(text):
    if not text: return ""
    text = re.sub(r'\s*\.\s*', '.', text)
    text = re.sub(r'\s*\,', ',', text)
    return text

def validate_hex_color(color_str):
    try:
        match = re.search(r'#(?:[0-9a-fA-F]{3}){1,2}', str(color_str))
        if match:
            hex_code = match.group(0)
            ImageColor.getrgb(hex_code) 
            return hex_code
        return "#FFD700"
    except: return "#FFD700"

def draw_rounded_box(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)

def create_glass_box(draw, xy, radius, fill=(0,0,0,160)):
    draw_rounded_box(draw, xy, radius, fill)

def create_smooth_gradient(width, height):
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        ratio = y / height
        if ratio > 0.3:
            alpha = int(255 * ((ratio - 0.3) / 0.7) ** 1.5)
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return overlay

def draw_text_with_shadow(draw, position, text, font, fill="white", shadow_color="black", offset=(2, 2)):
    x, y = position
    for ox in [-1, 1]:
        for oy in [-1, 1]:
            draw.text((x+ox, y+oy), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=fill)

def wrap_text(text, font, max_width, draw):
    lines = []
    text = clean_text_spacing(text)
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

def is_color_dark(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]) < 128
    except: return False

def paste_hybrid_logo(bg_img, symbol, logotxt, x=50, y=50, gap=15):
    next_x = x
    if symbol:
        bg_img.paste(symbol, (x, y), symbol)
        next_x += symbol.width + gap
    if logotxt:
        target_y = y
        if symbol:
            target_y = y + (symbol.height - logotxt.height) // 2
        bg_img.paste(logotxt, (next_x, target_y), logotxt)

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")

    # [NEW] 포맷 선택
    st.markdown("#### 📐 포맷(비율) 선택")
    format_option = st.radio("제작할 사이즈를 선택하세요:", ["카드뉴스 (1:1)", "인스타 스토리 (9:16)"])
    
    # 캔버스 사이즈 결정
    if "9:16" in format_option:
        CANVAS_W, CANVAS_H = 1080, 1920
        is_story = True
    else:
        CANVAS_W, CANVAS_H = 1080, 1080
        is_story = False
        
    st.markdown("---")
    
    st.markdown("#### 🎨 자산 설정")
    user_image = st.file_uploader("기사 사진 (1순위)", type=['png', 'jpg', 'jpeg'])
    
    # [NEW] 색상 추출 옵션
    use_auto_color = st.checkbox("📸 사진에서 테마 색상 자동 추출", value=True)
    
    up_symbol = st.file_uploader("세계일보 심볼 (AI/PNG)", type=['png', 'ai'])
    up_text_logo = st.file_uploader("세계일보 텍스트로고 (AI/PNG)", type=['png', 'ai'])
    
    with st.expander("폰트 수동 변경"):
        up_font_title = st.file_uploader("제목 폰트", type=['ttf', 'otf'])
        up_font_body = st.file_uploader("본문 폰트", type=['ttf', 'otf'])
        up_font_serif = st.file_uploader("명조 폰트", type=['ttf', 'otf'])

# --- 메인 ---
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

if st.button("🚀 카드뉴스 제작 (v11.0)"):
    if not api_key: st.error("API Key를 입력해주세요."); st.stop()
    if not url: st.error("URL을 입력해주세요."); st.stop()
    
    status = st.empty()
    status.info("📰 기사 분석 중...")
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- AI 기획 ---
    try:
        model_name = get_available_model()
        status.info(f"🤖 AI 기획 중... ({model_name})")
        model = genai.GenerativeModel(model_name)
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # [NEW] 프롬프트 고도화 (DATA 타입 추가)
        prompt = f"""
        당신은 세계일보의 뉴스 에디터입니다. 기사를 읽고 카드뉴스 8장을 기획하세요.
        [기사 제목] {title}
        [기사 내용] {text[:4000]}
        
        [필수 규칙]
        1. 무조건 8장(슬라이드)으로 구성.
        2. 각 장의 DESC(본문)는 80자 내외로 충실하게.
        3. **[중요] 기사에 숫자(%, 금액, 인원 등)가 핵심이라면 TYPE을 'DATA'로 지정하고 HEAD에 그 숫자만 적으세요.**
           (예: HEAD: 15%, DESC: 2026년 세계일보 구독률 상승폭...)
        
        [출력 포맷]
        COLOR_MAIN: #HexCode
        
        [SLIDE 1]
        TYPE: COVER
        HEAD: (제목)
        DESC: (요약)
        
        [SLIDE 2]
        TYPE: CONTENT (또는 DATA)
        HEAD: (소제목 또는 숫자)
        DESC: (내용)
        
        ... (3~7) ...
        
        [SLIDE 8]
        TYPE: OUTRO
        HEAD: First in, Last out
        DESC: 세상을 보는 눈, 세계일보
        """
        
        response = model.generate_content(prompt, safety_settings=safety_settings)
        res_text = response.text
        
        slides = []
        current_slide = {}
        ai_suggested_color = "#FFD700"
        
        for line in res_text.split('\n'):
            line = line.strip()
            if not line: continue
            clean_line = line.replace('*', '').replace('#', '').strip()
            
            if "COLOR_MAIN" in clean_line:
                parts = clean_line.split(":")
                if len(parts) > 1: ai_suggested_color = validate_hex_color(parts[1].strip())
            elif "[SLIDE" in clean_line:
                if current_slide: slides.append(current_slide)
                current_slide = {"HEAD": "", "DESC": "", "TYPE": "CONTENT"}
            elif "TYPE:" in clean_line:
                current_slide["TYPE"] = clean_line.split(":", 1)[1].strip()
            elif "HEAD:" in clean_line:
                current_slide["HEAD"] = clean_line.split(":", 1)[1].strip()
            elif "DESC:" in clean_line:
                current_slide["DESC"] = clean_line.split(":", 1)[1].strip()
        if current_slide: slides.append(current_slide)
        
        while len(slides) < 8:
            slides.append({"TYPE": "CONTENT", "HEAD": "내용 없음", "DESC": "AI 생성 오류"})
            
    except Exception as e: st.error(f"AI 기획 실패: {e}"); st.stop()

    # --- 이미지 생성 ---
    status.info("🎨 레이아웃 디자인 및 렌더링 중...")
    try:
        web_fonts = get_web_resources()
        def safe_font(font_bytes, size):
            try: return ImageFont.truetype(io.BytesIO(font_bytes), size)
            except: return ImageFont.load_default()

        font_title = safe_font(load_asset_bytes(up_font_title, ASSET_FILENAMES['font_title'], web_fonts['title']), 95)
        font_body = safe_font(load_asset_bytes(up_font_body, ASSET_FILENAMES['font_body'], web_fonts['body']), 48)
        font_small = safe_font(load_asset_bytes(up_font_body, ASSET_FILENAMES['font_body'], web_fonts['body']), 30)
        font_serif = safe_font(load_asset_bytes(up_font_serif, ASSET_FILENAMES['font_serif'], web_fonts['serif']), 90)
        # [NEW] 초대형 폰트 (데이터 시각화용)
        font_huge = safe_font(load_asset_bytes(up_font_title, ASSET_FILENAMES['font_title'], web_fonts['title']), 200)
        
        img_symbol = load_logo_image(up_symbol, ASSET_FILENAMES['symbol'], 60)
        img_logotxt = load_logo_image(up_text_logo, ASSET_FILENAMES['text'], 160)
        
        # [NEW] 이미지 로드 및 색상 추출
        if user_image:
            bg_raw = Image.open(user_image).convert('RGB')
        elif img_url:
            bg_raw = Image.open(io.BytesIO(requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).content)).convert('RGB')
        else:
            bg_raw = Image.new('RGB', (1080, 1080), color='#333333')
            
        # [NEW] 색상 결정 로직 (사진 색상 vs AI 추천 색상)
        if use_auto_color:
            color_main = get_dominant_color(bg_raw)
        else:
            color_main = ai_suggested_color

        # 캔버스 리사이징 (선택한 비율 적용)
        bg_raw = bg_raw.resize((CANVAS_W, CANVAS_H))
        
        bg_cover = bg_raw.copy()
        grad = create_smooth_gradient(CANVAS_W, CANVAS_H)
        bg_cover.paste(grad, (0,0), grad)
        
        bg_blur = bg_raw.copy().filter(ImageFilter.GaussianBlur(15))
        bg_blur = ImageEnhance.Brightness(bg_blur).enhance(0.6)
        
        try: bg_outro = Image.new('RGB', (CANVAS_W, CANVAS_H), color=color_main)
        except: bg_outro = Image.new('RGB', (CANVAS_W, CANVAS_H), color='#333333')
        
        generated_images = []
        tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
        title_color = "#FFFFFF" if is_color_dark(color_main) else color_main
        
        layout_pattern = ['BOX', 'BAR', 'QUOTE']
        random.shuffle(layout_pattern)
        
        for i, slide in enumerate(slides):
            sType = slide.get('TYPE', 'CONTENT')
            if sType == 'COVER': img = bg_cover.copy()
            elif sType == 'OUTRO': img = bg_outro.copy()
            else: img = bg_blur.copy()
            
            draw = ImageDraw.Draw(img, 'RGBA')
            
            # [공통] 로고 (스토리는 상단 여백 좀 더 확보)
            top_margin = 100 if is_story else 60
            if sType != 'OUTRO':
                if img_symbol or img_logotxt:
                    paste_hybrid_logo(img, img_symbol, img_logotxt, x=60, y=top_margin)
                else:
                    draw.text((60, top_margin), "SEGYE BRIEFING", font=font_small, fill=color_main)
                draw.text((CANVAS_W-130, top_margin), f"{i+1} / {len(slides)}", font=font_small, fill="white")

            # [1] COVER
            if sType == 'COVER':
                head = clean_text_spacing(slide.get('HEAD', ''))
                desc = clean_text_spacing(slide.get('DESC', ''))
                
                # 바닥부터 쌓아 올리기 (비율 무관하게 작동)
                d_lines = wrap_text(desc, font_body, CANVAS_W-100, draw)
                current_y = CANVAS_H - 150 - (len(d_lines) * 60)
                for line in d_lines:
                    draw_text_with_shadow(draw, (60, current_y), line, font_body, fill="#eeeeee")
                    current_y += 60
                
                current_y -= (len(d_lines)*60 + 40)
                draw.rectangle([(60, current_y), (160, current_y+10)], fill=color_main)
                
                h_lines = wrap_text(head, font_title, CANVAS_W-100, draw)
                current_y -= (len(h_lines) * 110 + 20)
                for line in h_lines:
                    draw_text_with_shadow(draw, (60, current_y), line, font_title, fill="white", offset=(4,4))
                    current_y += 110

            # [NEW] DATA TYPE (빅 넘버)
            elif sType == 'DATA':
                head = clean_text_spacing(slide.get('HEAD', '')) # 숫자
                desc = clean_text_spacing(slide.get('DESC', '')) # 설명
                
                # 숫자 중앙 배치
                bbox = draw.textbbox((0,0), head, font=font_huge)
                num_w = bbox[2] - bbox[0]
                num_h = bbox[3] - bbox[1]
                
                center_x = (CANVAS_W - num_w) // 2
                center_y = (CANVAS_H - num_h) // 2 - 100
                
                draw_text_with_shadow(draw, (center_x, center_y), head, font_huge, fill=color_main)
                
                # 설명 하단 배치
                d_lines = wrap_text(desc, font_body, 800, draw)
                desc_y = center_y + num_h + 50
                for line in d_lines:
                    lw = draw.textlength(line, font=font_body)
                    draw_text_with_shadow(draw, ((CANVAS_W-lw)//2, desc_y), line, font_body)
                    desc_y += 60

            # [2] CONTENT
            elif sType == 'CONTENT':
                layout = layout_pattern[i % 3]
                head = clean_text_spacing(slide.get('HEAD', ''))
                desc = clean_text_spacing(slide.get('DESC', ''))
                
                h_lines = wrap_text(head, font_title, CANVAS_W-180, draw)
                d_lines = wrap_text(desc, font_body, CANVAS_W-180, draw)
                
                if layout == 'BOX': 
                    box_h = (len(h_lines)*110) + (len(d_lines)*65) + 120
                    start_y = (CANVAS_H - box_h) // 2
                    draw_rounded_box(draw, (80, start_y, CANVAS_W-80, start_y + box_h), 30, (0,0,0,160))
                    txt_y = start_y + 50
                    for line in h_lines:
                        draw.text((120, txt_y), line, font=font_title, fill=title_color)
                        txt_y += 110
                    draw.line((120, txt_y+10, 320, txt_y+10), fill=title_color, width=5)
                    txt_y += 40
                    for line in d_lines:
                        draw.text((120, txt_y), line, font=font_body, fill="white")
                        txt_y += 65
                        
                elif layout == 'BAR': 
                    total_h = (len(h_lines)*110) + (len(d_lines)*65) + 60
                    start_y = (CANVAS_H - total_h) // 2
                    draw.rectangle([(80, start_y), (95, start_y + total_h)], fill=color_main)
                    txt_y = start_y
                    for line in h_lines:
                        draw_text_with_shadow(draw, (120, txt_y), line, font_title)
                        txt_y += 110
                    txt_y += 30
                    for line in d_lines:
                        draw_text_with_shadow(draw, (120, txt_y), line, font_body, fill="#dddddd")
                        txt_y += 65
                        
                elif layout == 'QUOTE': 
                    start_y = (CANVAS_H // 3)
                    draw.text((80, start_y - 150), "“", font=font_serif, fill=(255,255,255,50), font_size=300) 
                    for line in h_lines:
                        draw_text_with_shadow(draw, (150, start_y), line, font_title)
                        start_y += 110
                    draw.line((150, start_y+20, 350, start_y+20), fill=color_main, width=5)
                    start_y += 60
                    for line in d_lines:
                        draw_text_with_shadow(draw, (150, start_y), line, font_body, fill="#cccccc")
                        start_y += 65

            # [3] OUTRO
            elif sType == 'OUTRO':
                out_color = "white" if is_color_dark(color_main) else "black"
                slogan = "First in, Last out"
                bbox = draw.textbbox((0,0), slogan, font=font_serif)
                w = bbox[2] - bbox[0]
                draw.text(((CANVAS_W-w)/2, CANVAS_H//3), slogan, font=font_serif, fill=out_color)
                
                brand = "세상을 보는 눈, 세계일보"
                bbox2 = draw.textbbox((0,0), brand, font=font_body)
                w2 = bbox2[2] - bbox2[0]
                draw.text(((CANVAS_W-w2)/2, CANVAS_H//3 + 130), brand, font=font_body, fill=out_color)
                
                qr_img = generate_qr_code(url).resize((220, 220))
                qr_x = (CANVAS_W - 240) // 2
                qr_y = CANVAS_H//3 + 300
                draw.rounded_rectangle((qr_x, qr_y, qr_x+240, qr_y+240), radius=20, fill="white")
                img.paste(qr_img, (qr_x+10, qr_y+10))
                
                msg = "기사 원문 보러가기"
                bbox3 = draw.textbbox((0, 0), msg, font=font_small)
                w3 = bbox3[2] - bbox3[0]
                draw.text(((CANVAS_W-w3)/2, qr_y + 260), msg, font=font_small, fill=out_color)

            generated_images.append(img)
            with tabs[i]: st.image(img)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for i, img in enumerate(generated_images):
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                zf.writestr(f"card_{i+1:02d}.png", img_byte_arr.getvalue())
        
        st.success("✅ 제작 완료! 아래 버튼을 눌러 다운로드하세요.")
        st.download_button("💾 카드뉴스 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_news_intelligence.zip", "application/zip", use_container_width=True)

    except Exception as e: st.error(f"이미지 생성 중 오류 발생: {e}")
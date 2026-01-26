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
st.set_page_config(page_title="One-Click News v10.1", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v10.1 Ultimate Fallback)")
st.markdown("### 💎 4단계 모델 자동 우회 시스템 탑재")

# --- 기본 폰트 로드 ---
@st.cache_resource
def get_web_resources():
    resources = {}
    try:
        resources['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf", timeout=10).content
        resources['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        resources['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return resources

# --- 이미지 처리 유틸리티 ---
def load_image_from_upload(uploaded_file, width_target):
    if not uploaded_file: return None
    try:
        data = uploaded_file.getvalue()
        if uploaded_file.name.lower().endswith('.ai'):
            doc = fitz.open(stream=data, filetype="pdf")
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=True)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
        else:
            img = Image.open(io.BytesIO(data)).convert("RGBA")
        ar = img.height / img.width
        return img.resize((width_target, int(width_target * ar)))
    except: return None

def validate_hex_color(color_str):
    try:
        match = re.search(r'#(?:[0-9a-fA-F]{3}){1,2}', str(color_str))
        if match:
            hex_code = match.group(0)
            ImageColor.getrgb(hex_code) 
            return hex_code
        return "#FFD700"
    except: return "#FFD700"

def create_glass_box(draw, xy, radius, fill=(0,0,0,160)):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)

def create_smooth_gradient(width, height):
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        ratio = y / height
        if ratio > 0.3:
            alpha = int(255 * ((ratio - 0.3) / 0.7) ** 2)
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

# --- 스크래핑 ---
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
    if len(text) < 50:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            if not title: title = soup.find('title').text.strip()
            meta = soup.find('meta', property='og:image')
            if meta: top_image = meta['content']
            text = soup.get_text(separator=' ', strip=True)[:5000]
        except: pass
    return title, text, top_image

# --- [핵심] 4단계 모델 우회 생성 함수 ---
def generate_content_with_fallback(prompt):
    # 우선순위: 최신 Flash -> 1.5 Pro -> 1.0 Pro -> 구형 Pro
    models_to_try = [
        "gemini-1.5-flash", 
        "gemini-1.5-pro", 
        "gemini-1.0-pro", 
        "gemini-pro"
    ]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    last_error = None
    
    for model_name in models_to_try:
        try:
            # st.write(f"Testing model: {model_name}...") # 디버깅용
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt, safety_settings=safety_settings)
            return response.text # 성공하면 즉시 반환
        except Exception as e:
            last_error = e
            continue # 실패하면 다음 모델 시도
            
    # 모든 모델 실패 시 에러 발생
    raise last_error

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")
    
    st.markdown("#### 1. 필수 이미지")
    user_image = st.file_uploader("기사 배경 사진 (JPG/PNG)", type=['png', 'jpg', 'jpeg'])
    
    st.markdown("#### 2. 로고 설정 (필수!)")
    symbol_file = st.file_uploader("세계일보 심볼 (AI/PNG)", type=['png', 'ai'])
    text_logo_file = st.file_uploader("세계일보 텍스트로고 (AI/PNG)", type=['png', 'ai'])
    
    if not symbol_file or not text_logo_file:
        st.error("⚠️ 로고 파일을 업로드해야 카드뉴스에 적용됩니다!")

# --- 메인 로직 ---
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

if st.button("🚀 카드뉴스 제작 (v10.1)"):
    if not api_key: st.error("API Key를 입력해주세요."); st.stop()
    if not url: st.error("URL을 입력해주세요."); st.stop()
    
    # 1. 기사 분석
    status = st.empty()
    status.info("📰 기사 내용을 읽고 있습니다...")
    title, text, img_url = advanced_scrape(url)
    
    if len(text) < 50:
        st.error("기사 본문을 가져오지 못했습니다. URL을 확인해주세요.")
        st.stop()

    # 2. AI 기획 (자동 우회 적용)
    status.info("🧠 AI가 최적의 모델을 찾아 기획 중입니다...")
    try:
        prompt = f"""
        당신은 세계일보의 뉴스 에디터입니다. 기사를 읽고 카드뉴스 8장을 기획하세요.
        
        [기사 제목] {title}
        [기사 내용] {text[:4000]}
        
        [필수 규칙]
        1. 무조건 8장(슬라이드)으로 구성하세요.
        2. 출력 형식은 아래 포맷을 **정확히** 지키세요.
        3. 각 슬라이드의 'DESC'(설명)는 2~3문장으로 충실하게 작성하세요.
        
        [출력 포맷]
        COLOR_MAIN: #대표색상코드
        
        [SLIDE 1]
        TYPE: COVER
        HEAD: (제목 15자 이내)
        DESC: (부제/요약 40자 이내)
        
        [SLIDE 2]
        TYPE: CONTENT
        HEAD: (소제목)
        DESC: (본문 내용 - 80자 내외)
        
        ... (3~7 반복) ...
        
        [SLIDE 8]
        TYPE: OUTRO
        HEAD: First in, Last out
        DESC: 세상을 보는 눈, 세계일보
        """
        
        # [핵심] 여기서 4단계 우회 함수 호출
        res_text = generate_content_with_fallback(prompt)
        
        # 파싱
        slides = []
        current_slide = {}
        color_main = "#FFD700"
        
        lines = res_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            
            clean_line = line.replace('*', '').replace('#', '').strip()
            
            if "COLOR_MAIN" in clean_line:
                parts = clean_line.split(":")
                if len(parts) > 1:
                    color_main = validate_hex_color(parts[1].strip())
            
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
            slides.append({"TYPE": "CONTENT", "HEAD": "내용 없음", "DESC": "AI 내용 누락"})
            
    except Exception as e:
        st.error(f"모든 AI 모델 연결 실패: {e}")
        st.stop()

    # 3. 이미지 생성
    status.info("🎨 이미지를 렌더링하고 있습니다...")
    try:
        web_fonts = get_web_resources()
        font_title = ImageFont.truetype(io.BytesIO(web_fonts['title']), 95)
        font_body = ImageFont.truetype(io.BytesIO(web_fonts['body']), 48)
        font_small = ImageFont.truetype(io.BytesIO(web_fonts['body']), 30)
        font_serif = ImageFont.truetype(io.BytesIO(web_fonts['serif']), 90)
        
        img_symbol = load_image_from_upload(symbol_file, 60)
        img_logotxt = load_image_from_upload(text_logo_file, 160)
        
        if user_image:
            bg_raw = Image.open(user_image).convert('RGB')
        elif img_url:
            bg_raw = Image.open(io.BytesIO(requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).content)).convert('RGB')
        else:
            bg_raw = Image.new('RGB', (1080, 1080), color='#333333')
        bg_raw = bg_raw.resize((1080, 1080))
        
        bg_cover = bg_raw.copy()
        grad = create_smooth_gradient(1080, 1080)
        bg_cover.paste(grad, (0,0), grad)
        
        bg_blur = bg_raw.copy().filter(ImageFilter.GaussianBlur(15))
        bg_blur = ImageEnhance.Brightness(bg_blur).enhance(0.6)
        
        try: bg_outro = Image.new('RGB', (1080, 1080), color=color_main)
        except: bg_outro = Image.new('RGB', (1080, 1080), color='#333333')
        
        generated_images = []
        tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
        
        title_color = "#FFFFFF" if is_color_dark(color_main) else color_main
        
        for i, slide in enumerate(slides):
            sType = slide.get('TYPE', 'CONTENT')
            if sType == 'COVER': img = bg_cover.copy()
            elif sType == 'OUTRO': img = bg_outro.copy()
            else: img = bg_blur.copy()
            
            draw = ImageDraw.Draw(img, 'RGBA')
            
            if sType != 'OUTRO':
                if img_symbol or img_logotxt:
                    paste_hybrid_logo(img, img_symbol, img_logotxt, x=50, y=50)
                else:
                    draw.text((50, 50), "SEGYE BRIEFING", font=font_small, fill=color_main)
                draw.text((950, 60), f"{i+1} / {len(slides)}", font=font_small, fill="white")

            if sType == 'COVER':
                head = slide.get('HEAD', '')
                desc = slide.get('DESC', '')
                d_lines = wrap_text(desc, font_body, 980, draw)
                current_y = 1080 - 120 - (len(d_lines) * 60)
                for line in d_lines:
                    draw_text_with_shadow(draw, (50, current_y), line, font_body, fill="#eeeeee")
                    current_y += 60
                current_y -= (len(d_lines)*60 + 40)
                draw.rectangle([(50, current_y), (150, current_y+10)], fill=color_main)
                h_lines = wrap_text(head, font_title, 980, draw)
                current_y -= (len(h_lines) * 110 + 20)
                for line in h_lines:
                    draw_text_with_shadow(draw, (50, current_y), line, font_title, fill="white", offset=(4,4))
                    current_y += 110

            elif sType == 'CONTENT':
                head = slide.get('HEAD', '')
                desc = slide.get('DESC', '')
                h_lines = wrap_text(head, font_title, 850, draw)
                d_lines = wrap_text(desc, font_body, 850, draw)
                box_h = (len(h_lines)*110) + (len(d_lines)*65) + 120
                start_y = (1080 - box_h) // 2
                create_glass_box(draw, (80, start_y, 1000, start_y + box_h), 30)
                txt_y = start_y + 50
                for line in h_lines:
                    draw.text((120, txt_y), line, font=font_title, fill=title_color)
                    txt_y += 110
                draw.line((120, txt_y+10, 320, txt_y+10), fill=title_color, width=5)
                txt_y += 40
                for line in d_lines:
                    draw.text((120, txt_y), line, font_body, fill="white")
                    txt_y += 65

            elif sType == 'OUTRO':
                out_color = "white" if is_color_dark(color_main) else "black"
                slogan = "First in, Last out"
                bbox = draw.textbbox((0,0), slogan, font=font_serif)
                w = bbox[2] - bbox[0]
                draw.text(((1080-w)/2, 350), slogan, font=font_serif, fill=out_color)
                brand = "세상을 보는 눈, 세계일보"
                bbox2 = draw.textbbox((0,0), brand, font=font_body)
                w2 = bbox2[2] - bbox2[0]
                draw.text(((1080-w2)/2, 480), brand, font=font_body, fill=out_color)
                qr_img = generate_qr_code(url).resize((220, 220))
                qr_x = (1080 - 240) // 2
                qr_y = 650
                draw.rounded_rectangle((qr_x, qr_y, qr_x+240, qr_y+240), radius=20, fill="white")
                img.paste(qr_img, (qr_x+10, qr_y+10))
            
            generated_images.append(img)
            with tabs[i]: st.image(img)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for i, img in enumerate(generated_images):
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                zf.writestr(f"card_{i+1:02d}.png", img_byte_arr.getvalue())
        
        st.success("✅ 제작 완료! 아래 버튼을 눌러 다운로드하세요.")
        st.download_button("💾 카드뉴스 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_news_ultimate.zip", "application/zip", use_container_width=True)

    except Exception as e:
        st.error(f"이미지 생성 중 오류 발생: {e}")
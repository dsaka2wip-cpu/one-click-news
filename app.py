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

# --- [1] 페이지 설정 ---
st.set_page_config(page_title="One-Click News v12.2", page_icon="📰", layout="wide")

# --- [2] 고정 자산 설정 (파일명을 상수로 정의) ---
# ※ 이 파일들이 app.py와 같은 폴더에 있어야 합니다.
LOGO_SYMBOL_PATH = "segye_symbol.png"
LOGO_TEXT_PATH = "segye_text.png"

# ==============================================================================
# [3] 함수 정의 구역
# ==============================================================================

# 3-1. 폰트 안정화 (로컬 저장 방식)
@st.cache_resource
def load_fonts_local():
    """폰트를 서버 로컬 폴더에 다운로드하여 안정성을 확보합니다."""
    font_dir = "fonts"
    if not os.path.exists(font_dir):
        os.makedirs(font_dir)
        
    fonts = {
        'title': "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-ExtraBold.ttf",
        'body': "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf",
        'serif': "https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf"
    }
    
    paths = {}
    for key, url in fonts.items():
        filename = os.path.join(font_dir, f"{key}.ttf")
        if not os.path.exists(filename):
            try:
                resp = requests.get(url, timeout=10)
                with open(filename, "wb") as f:
                    f.write(resp.content)
            except:
                pass # 실패 시 None 처리
        paths[key] = filename if os.path.exists(filename) else None
        
    return paths

# 3-2. 로컬 이미지 로드 (로고용)
def load_local_image(path, width_target):
    if not os.path.exists(path):
        return None
    try:
        img = Image.open(path).convert("RGBA")
        ar = img.height / img.width
        return img.resize((width_target, int(width_target * ar)))
    except:
        return None

# 3-3. 스크래핑 함수 (이미지 다중 추출)
def advanced_scrape(url):
    title, text, top_image = "", "", ""
    images = [] 
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0'
        config.request_timeout = 10
        article = Article(url, config=config)
        article.download()
        article.parse()
        title, text, top_image = article.title, article.text, article.top_image
        images = list(article.images)
    except: pass
    
    if len(text) < 50:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            if not title: title = soup.find('title').text.strip()
            if not top_image:
                meta = soup.find('meta', property='og:image')
                if meta: top_image = meta['content']
            text = soup.get_text(separator=' ', strip=True)[:5000]
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and src.startswith('http'): images.append(src)
        except: pass
    
    valid_images = [top_image] if top_image else []
    for img in images:
        if img not in valid_images and 'icon' not in img and 'logo' not in img:
            valid_images.append(img)
            
    return title, text, valid_images

# 3-4. 색상 추출
def get_dominant_color(pil_img):
    try:
        img = pil_img.copy()
        img = img.convert("P", palette=Image.ADAPTIVE, colors=1)
        palette = img.getpalette()
        color = palette[:3]
        return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
    except: return "#FFD700"

# 3-5. 모델 자동 탐색
def get_available_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priorities = ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-1.0-pro", "models/gemini-pro"]
        for p in priorities:
            for m in models:
                if p in m: return m
        return models[0] if models else "models/gemini-pro"
    except: return "models/gemini-pro"

# 3-6. 디자인 유틸리티
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
    for ox in [-2, 0, 2]:
        for oy in [-2, 0, 2]:
            if ox == 0 and oy == 0: continue
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

# ==============================================================================
# [4] 사이드바 UI
# ==============================================================================
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")

    st.markdown("#### 📐 포맷(비율) 선택")
    format_option = st.radio("제작할 사이즈를 선택하세요:", ["카드뉴스 (1:1)", "인스타 스토리 (9:16)"])
    
    if "9:16" in format_option:
        CANVAS_W, CANVAS_H = 1080, 1920
        is_story = True
    else:
        CANVAS_W, CANVAS_H = 1080, 1080
        is_story = False
        
    st.markdown("---")
    
    st.markdown("#### 🎨 자산 설정")
    user_image = st.file_uploader("대표 이미지 (선택)", type=['png', 'jpg', 'jpeg'])
    use_auto_color = st.checkbox("📸 사진에서 테마 색상 자동 추출", value=True)
    
    # [수정] 로고 업로더 제거됨 (자동 로드)
    if os.path.exists(LOGO_SYMBOL_PATH) and os.path.exists(LOGO_TEXT_PATH):
        st.success("✅ 세계일보 로고 파일이 감지되었습니다.")
    else:
        st.warning("⚠️ 로고 파일(segye_symbol.png, segye_text.png)이 폴더에 없습니다.")

# ==============================================================================
# [5] 메인 UI (순서 변경: URL 입력 -> 안내)
# ==============================================================================
st.title("📰 One-Click News (v12.2 UX Fixed)")

# 1. URL 입력창을 최상단으로
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

# 2. 안내문은 아래로 (접힌 상태로 시작)
with st.expander("💡 [안내] 세계일보 AI 카드뉴스 생성 원리 & 기능 명세", expanded=False):
    st.markdown("""
    이 프로그램은 단순한 요약기가 아닙니다. **세계일보의 저널리즘 원칙**과 **최신 생성형 AI 기술**이 결합된 지능형 제작 도구입니다.
    
    ### 🧠 1. Intelligence (맥락 인식 기획)
    * **내러티브 구조화:** 기사를 기계적으로 줄이지 않고, **'Hook(유입) - Content(전개) - Conclusion(결론)'**의 8단 구성으로 재창조합니다.
    * **데이터 감지 (Big Number):** 기사 내 핵심 수치(%, 금액 등)가 감지되면, 이를 자동으로 포착하여 **인포그래픽(Data Visualization)** 슬라이드로 변환합니다.
    * **모델 자동 우회 (Auto-Pilot):** 구글의 최신 AI 모델을 자동 탐색하여 연결 실패를 방지합니다.

    ### 🎨 2. Design Engine (유동적 디자인)
    * **멀티 포맷 지원:** 하나의 기사로 **인스타그램 피드(1:1)**와 **스토리/릴스(9:16)** 포맷을 즉시 전환하여 생성합니다.
    * **지능형 컬러 피킹 (Auto Color):** 업로드된 보도사진의 **지배적인 색상(Dominant Color)**을 AI가 분석·추출하여, 사진과 가장 잘 어울리는 테마 컬러를 자동 적용합니다.
    * **레이아웃 변주 시스템:** 텍스트 분량과 성격에 따라 **[박스형 / 바형 / 인용구형 / 빅넘버형]** 4가지 디자인을 유기적으로 섞어 지루함을 없앴습니다.

    ### 🛡️ 3. Core Tech (안정성 & 디테일)
    * **자동 자산 로드:** 로고 파일을 매번 올릴 필요 없이, 서버에 저장된 고화질 로고를 자동으로 불러옵니다.
    * **스마트 디밍 (Smart Dimming):** 배경 사진이 밝아도 흰색 글씨가 선명하게 보이도록, 이미지의 밝기를 자동으로 조절합니다.
    * **Visual SEO:** 인스타그램 등 소셜 미디어 유입을 극대화하기 위한 해시태그를 자동 생성합니다.
    """)

# ==============================================================================
# [6] 메인 실행 로직
# ==============================================================================
if st.button("🚀 카드뉴스 제작"):
    if not api_key: st.error("API Key를 입력해주세요."); st.stop()
    if not url: st.error("URL을 입력해주세요."); st.stop()
    
    status = st.empty()
    status.info("📰 기사 분석 및 이미지 수집 중...")
    
    title, text, scraped_images = advanced_scrape(url)
    
    if len(text) < 50:
        st.error("기사 본문을 가져오지 못했습니다.")
        st.stop()

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

        prompt = f"""
        당신은 세계일보의 뉴스 에디터입니다. 기사를 읽고 카드뉴스 8장을 기획하세요.
        [기사 제목] {title}
        [기사 내용] {text[:4000]}
        
        [필수 규칙]
        1. 무조건 8장(슬라이드)으로 구성.
        2. 각 장의 DESC(본문)는 80자 내외로 충실하게.
        3. 기사에 숫자가 핵심이라면 TYPE을 'DATA'로 지정.
        4. 마지막에 인스타그램용 해시태그 5개를 추천해주세요.
        
        [출력 포맷]
        COLOR_MAIN: #HexCode
        HASHTAGS: #태그1 #태그2 ...
        
        [SLIDE 1]
        TYPE: COVER
        HEAD: (제목)
        DESC: (요약)
        
        ... (중략) ...
        
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
        hashtags = ""
        
        for line in res_text.split('\n'):
            line = line.strip()
            if not line: continue
            clean_line = line.replace('*', '').replace('#', '').strip()
            
            if "COLOR_MAIN" in clean_line:
                parts = clean_line.split(":")
                if len(parts) > 1: ai_suggested_color = validate_hex_color(parts[1].strip())
            
            elif "HASHTAGS" in clean_line:
                try: hashtags = line.split(":", 1)[1].strip()
                except: hashtags = line
                
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
        # [중요] 폰트 로컬 로드 (깨짐 방지)
        font_paths = load_fonts_local()
        
        def safe_font(path, size):
            try: return ImageFont.truetype(path, size)
            except: return ImageFont.load_default()

        font_title = safe_font(font_paths['title'], 95)
        font_body = safe_font(font_paths['body'], 48)
        font_small = safe_font(font_paths['body'], 30)
        font_serif = safe_font(font_paths['serif'], 90)
        font_huge = safe_font(font_paths['title'], 200)
        
        # [중요] 로고 로컬 로드
        img_symbol = load_local_image(LOGO_SYMBOL_PATH, 60)
        img_logotxt = load_local_image(LOGO_TEXT_PATH, 160)
        
        final_images_pool = []
        
        if user_image:
            img_bytes = user_image.getvalue()
            final_images_pool.append(Image.open(io.BytesIO(img_bytes)).convert('RGB'))
        elif scraped_images:
            for img_link in scraped_images[:5]:
                try:
                    resp = requests.get(img_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                    final_images_pool.append(Image.open(io.BytesIO(resp.content)).convert('RGB'))
                except: continue
        
        if not final_images_pool:
            final_images_pool.append(Image.new('RGB', (1080, 1080), color='#333333'))

        if use_auto_color:
            color_main = get_dominant_color(final_images_pool[0])
        else:
            color_main = ai_suggested_color

        # 아웃트로 배경
        try: bg_outro = Image.new('RGB', (CANVAS_W, CANVAS_H), color=color_main)
        except: bg_outro = Image.new('RGB', (CANVAS_W, CANVAS_H), color='#333333')
        
        generated_images = []
        tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
        title_color = "#FFFFFF" if is_color_dark(color_main) else color_main
        
        layout_pattern = ['BOX', 'BAR', 'QUOTE']
        random.shuffle(layout_pattern)
        
        for i, slide in enumerate(slides):
            sType = slide.get('TYPE', 'CONTENT')
            
            # 배경 이미지 할당
            if sType == 'OUTRO':
                img = bg_outro.copy()
            else:
                pool_idx = 0 if sType == 'COVER' else i % len(final_images_pool)
                base_img = final_images_pool[pool_idx].copy().resize((CANVAS_W, CANVAS_H))
                
                if sType == 'COVER':
                    grad = create_smooth_gradient(CANVAS_W, CANVAS_H)
                    base_img.paste(grad, (0,0), grad)
                    img = base_img
                else:
                    img = base_img.filter(ImageFilter.GaussianBlur(15))
                    img = ImageEnhance.Brightness(img).enhance(0.4)

            draw = ImageDraw.Draw(img, 'RGBA')
            
            # 로고 배치
            top_margin = 100 if is_story else 60
            if sType != 'OUTRO':
                if img_symbol or img_logotxt:
                    paste_hybrid_logo(img, img_symbol, img_logotxt, x=60, y=top_margin)
                else:
                    draw.text((60, top_margin), "SEGYE BRIEFING", font=font_small, fill=color_main)
                draw.text((CANVAS_W-130, top_margin), f"{i+1} / {len(slides)}", font=font_small, fill="white")

            if sType == 'COVER':
                head = clean_text_spacing(slide.get('HEAD', ''))
                desc = clean_text_spacing(slide.get('DESC', ''))
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

            elif sType == 'DATA':
                head = clean_text_spacing(slide.get('HEAD', ''))
                desc = clean_text_spacing(slide.get('DESC', ''))
                bbox = draw.textbbox((0,0), head, font=font_huge)
                num_w = bbox[2] - bbox[0]
                num_h = bbox[3] - bbox[1]
                center_x = (CANVAS_W - num_w) // 2
                center_y = (CANVAS_H - num_h) // 2 - 100
                draw_text_with_shadow(draw, (center_x, center_y), head, font_huge, fill=color_main)
                d_lines = wrap_text(desc, font_body, 800, draw)
                desc_y = center_y + num_h + 50
                for line in d_lines:
                    lw = draw.textlength(line, font=font_body)
                    draw_text_with_shadow(draw, ((CANVAS_W-lw)//2, desc_y), line, font_body)
                    desc_y += 60

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
        
        st.success("✅ 제작 완료! 해시태그를 복사해서 쓰세요.")
        st.code(hashtags, language="text")
        
        st.download_button("💾 카드뉴스 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_news_visual.zip", "application/zip", use_container_width=True)

    except Exception as e: st.error(f"이미지 생성 중 오류 발생: {e}")
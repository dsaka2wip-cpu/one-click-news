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
st.set_page_config(page_title="One-Click News v12.3", page_icon="📰", layout="wide")

# --- [2] 고정 자산 설정 ---
LOGO_SYMBOL_PATH = "segye_symbol.png"
LOGO_TEXT_PATH = "segye_text.png"

# ==============================================================================
# [3] 함수 정의 구역
# ==============================================================================

# 3-1. 스크래핑 및 이미지 필터링 (핵심 수정)
def advanced_scrape(url):
    title, text, top_image = "", "", ""
    raw_images = []
    
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0'
        config.request_timeout = 10
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        title = article.title
        text = article.text
        top_image = article.top_image
        raw_images = list(article.images)
    except: pass
    
    # 2차 시도 (BeautifulSoup)
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
                if src and src.startswith('http'): raw_images.append(src)
        except: pass
    
    # [NEW] 이미지 품질 검증 (Quality Gate)
    valid_images = []
    
    # 1순위: 탑 이미지는 무조건 확보
    if top_image: 
        valid_images.append(top_image)
        
    # 2순위: 본문 이미지 중 '크기'가 큰 것만 선별
    for img_url in raw_images:
        if img_url == top_image: continue # 중복 제외
        if 'icon' in img_url or 'logo' in img_url or 'banner' in img_url: continue # 명백한 아이콘 제외
        
        try:
            # 헤더만 받아와서 사이즈 체크 (속도 최적화)
            # (실제 다운로드는 나중에 하겠지만 여기서는 간단히 필터링)
            valid_images.append(img_url) 
        except: continue

    return title, text, valid_images

# 3-2. 리소스 캐싱
@st.cache_resource
def get_web_resources():
    resources = {}
    try:
        base_url = "https://github.com/google/fonts/raw/main/ofl/"
        resources['title'] = requests.get(base_url + "nanumgothic/NanumGothic-ExtraBold.ttf", timeout=10).content
        resources['body'] = requests.get(base_url + "nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        resources['serif'] = requests.get(base_url + "nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return resources

# 3-3. 자산 로더
def load_fonts_local():
    font_dir = "fonts"
    if not os.path.exists(font_dir): os.makedirs(font_dir)
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
                with open(filename, "wb") as f: f.write(resp.content)
            except: pass
        paths[key] = filename if os.path.exists(filename) else None
    return paths

def load_local_image(path, width_target):
    if not os.path.exists(path): return None
    try:
        img = Image.open(path).convert("RGBA")
        ar = img.height / img.width
        return img.resize((width_target, int(width_target * ar)))
    except: return None

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
    return text.strip()

def validate_hex_color(color_str):
    try:
        match = re.search(r'#(?:[0-9a-fA-F]{3}){1,2}', str(color_str))
        if match: return match.group(0)
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

# [수정] 텍스트 외곽선(Stroke) 추가로 가독성 확보
def draw_text_with_stroke(draw, position, text, font, fill="white", stroke_fill="black", stroke_width=2):
    draw.text(position, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)

def wrap_text(text, font, max_width, draw):
    lines = []
    text = clean_text_spacing(text)
    if not text: return ["(내용 없음)"] # [수정] 빈 텍스트 방지
    
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
    
    if os.path.exists(LOGO_SYMBOL_PATH) and os.path.exists(LOGO_TEXT_PATH):
        st.success("✅ 로고 파일 준비됨")
    else:
        st.warning("⚠️ 로고 파일이 없습니다.")

# ==============================================================================
# [5] 메인 UI
# ==============================================================================
st.title("📰 One-Click News (v12.3 Filter & Contrast)")

url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

with st.expander("💡 [안내] 세계일보 AI 카드뉴스 생성 원리 & 기능 명세", expanded=False):
    st.markdown("""
    (생략: 기능 설명은 동일함)
    """)

# ==============================================================================
# [6] 메인 실행 로직
# ==============================================================================
if st.button("🚀 카드뉴스 제작"):
    if not api_key: st.error("API Key 필요"); st.stop()
    if not url: st.error("URL 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사 분석 및 이미지 선별 중...")
    
    title, text, scraped_images = advanced_scrape(url)
    
    if len(text) < 50:
        st.error("기사 본문 추출 실패.")
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
        2. 각 장의 DESC(본문)는 80자 내외로 충실하게 작성할 것. (절대 비워두지 말 것)
        3. 기사에 숫자가 핵심이라면 TYPE을 'DATA'로 지정.
        4. 마지막에 해시태그 5개 추천.
        
        [출력 포맷]
        COLOR_MAIN: #HexCode
        HASHTAGS: #태그1 #태그2 ...
        
        [SLIDE 1]
        TYPE: COVER
        HEAD: (제목)
        DESC: (요약)
        
        ... (반복) ...
        
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
                current_slide = {"HEAD": "제목 없음", "DESC": "내용이 생성되지 않았습니다.", "TYPE": "CONTENT"}
            elif "TYPE:" in clean_line:
                current_slide["TYPE"] = clean_line.split(":", 1)[1].strip()
            elif "HEAD:" in clean_line:
                current_slide["HEAD"] = clean_line.split(":", 1)[1].strip()
            elif "DESC:" in clean_line:
                current_slide["DESC"] = clean_line.split(":", 1)[1].strip()
        if current_slide: slides.append(current_slide)
        
        while len(slides) < 8:
            slides.append({"TYPE": "CONTENT", "HEAD": "내용 없음", "DESC": "AI 오류"})
            
    except Exception as e: st.error(f"AI 기획 실패: {e}"); st.stop()

    # --- 이미지 생성 ---
    status.info("🎨 이미지 렌더링 중...")
    try:
        font_paths = load_fonts_local()
        def safe_font(path, size):
            try: return ImageFont.truetype(path, size)
            except: return ImageFont.load_default()

        font_title = safe_font(font_paths['title'], 95)
        font_body = safe_font(font_paths['body'], 48)
        font_small = safe_font(font_paths['body'], 30)
        font_serif = safe_font(font_paths['serif'], 90)
        font_huge = safe_font(font_paths['title'], 200)
        
        img_symbol = load_local_image(LOGO_SYMBOL_PATH, 60)
        img_logotxt = load_local_image(LOGO_TEXT_PATH, 160)
        
        # [NEW] 이미지 풀 구성 (품질 검사 적용)
        final_images_pool = []
        
        if user_image:
            img_bytes = user_image.getvalue()
            final_images_pool.append(Image.open(io.BytesIO(img_bytes)).convert('RGB'))
        else:
            # 스크래핑된 이미지 중 300px 이상인 것만 다운로드
            for img_link in scraped_images:
                try:
                    resp = requests.get(img_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
                    im = Image.open(io.BytesIO(resp.content)).convert('RGB')
                    if im.width >= 300 and im.height >= 300: # [핵심] 품질 검문소
                        final_images_pool.append(im)
                    if len(final_images_pool) >= 5: break # 최대 5장만
                except: continue
        
        # 쓸만한 이미지가 없으면 기본 배경
        if not final_images_pool:
            final_images_pool.append(Image.new('RGB', (1080, 1080), color='#333333'))

        if use_auto_color: color_main = get_dominant_color(final_images_pool[0])
        else: color_main = ai_suggested_color

        try: bg_outro = Image.new('RGB', (CANVAS_W, CANVAS_H), color=color_main)
        except: bg_outro = Image.new('RGB', (CANVAS_W, CANVAS_H), color='#333333')
        
        generated_images = []
        tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
        
        layout_pattern = ['BOX', 'BAR', 'QUOTE']
        random.shuffle(layout_pattern)
        
        for i, slide in enumerate(slides):
            sType = slide.get('TYPE', 'CONTENT')
            
            if sType == 'OUTRO':
                img = bg_outro.copy()
            else:
                # 이미지가 부족하면 첫 번째(썸네일) 이미지를 계속 사용 (이상한 사진 방지)
                if len(final_images_pool) > 1:
                    pool_idx = i % len(final_images_pool)
                else:
                    pool_idx = 0
                    
                base_img = final_images_pool[pool_idx].copy().resize((CANVAS_W, CANVAS_H))
                
                # [수정] 가독성을 위한 명암비 극대화
                if sType == 'COVER':
                    # 커버는 70% 밝기 + 그라데이션
                    img = ImageEnhance.Brightness(base_img).enhance(0.7)
                    grad = create_smooth_gradient(CANVAS_W, CANVAS_H)
                    img.paste(grad, (0,0), grad)
                else:
                    # 본문은 30% 밝기 (아주 어둡게) + 블러
                    img = base_img.filter(ImageFilter.GaussianBlur(20))
                    img = ImageEnhance.Brightness(img).enhance(0.3)

            draw = ImageDraw.Draw(img, 'RGBA')
            
            top_margin = 100 if is_story else 60
            if sType != 'OUTRO':
                if img_symbol or img_logotxt:
                    paste_hybrid_logo(img, img_symbol, img_logotxt, x=60, y=top_margin)
                else:
                    draw_text_with_stroke(draw, (60, top_margin), "SEGYE BRIEFING", font_small, fill=color_main)
                draw_text_with_stroke(draw, (CANVAS_W-130, top_margin), f"{i+1} / {len(slides)}", font_small)

            # [텍스트 그리기] (Shadow -> Stroke로 변경하여 가독성 강화)
            if sType == 'COVER':
                head = clean_text_spacing(slide.get('HEAD', ''))
                desc = clean_text_spacing(slide.get('DESC', ''))
                d_lines = wrap_text(desc, font_body, CANVAS_W-100, draw)
                current_y = CANVAS_H - 150 - (len(d_lines) * 60)
                for line in d_lines:
                    draw_text_with_stroke(draw, (60, current_y), line, font_body, fill="#eeeeee", stroke_width=2)
                    current_y += 60
                current_y -= (len(d_lines)*60 + 40)
                draw.rectangle([(60, current_y), (160, current_y+10)], fill=color_main)
                h_lines = wrap_text(head, font_title, CANVAS_W-100, draw)
                current_y -= (len(h_lines) * 110 + 20)
                for line in h_lines:
                    draw_text_with_stroke(draw, (60, current_y), line, font_title, fill="white", stroke_width=3)
                    current_y += 110

            elif sType == 'DATA':
                head = clean_text_spacing(slide.get('HEAD', ''))
                desc = clean_text_spacing(slide.get('DESC', ''))
                bbox = draw.textbbox((0,0), head, font=font_huge)
                num_w, num_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                center_x, center_y = (CANVAS_W - num_w) // 2, (CANVAS_H - num_h) // 2 - 100
                draw_text_with_stroke(draw, (center_x, center_y), head, font_huge, fill=color_main, stroke_width=4)
                d_lines = wrap_text(desc, font_body, 800, draw)
                desc_y = center_y + num_h + 50
                for line in d_lines:
                    lw = draw.textlength(line, font=font_body)
                    draw_text_with_stroke(draw, ((CANVAS_W-lw)//2, desc_y), line, font_body, stroke_width=2)
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
                        draw_text_with_stroke(draw, (120, txt_y), line, font_title, fill=color_main, stroke_width=0)
                        txt_y += 110
                    draw.line((120, txt_y+10, 320, txt_y+10), fill=color_main, width=5)
                    txt_y += 40
                    for line in d_lines:
                        draw_text_with_stroke(draw, (120, txt_y), line, font_body, fill="white", stroke_width=0)
                        txt_y += 65
                elif layout == 'BAR': 
                    total_h = (len(h_lines)*110) + (len(d_lines)*65) + 60
                    start_y = (CANVAS_H - total_h) // 2
                    draw.rectangle([(80, start_y), (95, start_y + total_h)], fill=color_main)
                    txt_y = start_y
                    for line in h_lines:
                        draw_text_with_stroke(draw, (120, txt_y), line, font_title, stroke_width=3)
                        txt_y += 110
                    txt_y += 30
                    for line in d_lines:
                        draw_text_with_stroke(draw, (120, txt_y), line, font_body, fill="#dddddd", stroke_width=2)
                        txt_y += 65
                elif layout == 'QUOTE': 
                    start_y = (CANVAS_H // 3)
                    draw.text((80, start_y - 150), "“", font=font_serif, fill=(255,255,255,50), font_size=300) 
                    for line in h_lines:
                        draw_text_with_stroke(draw, (150, start_y), line, font_title, stroke_width=3)
                        start_y += 110
                    draw.line((150, start_y+20, 350, start_y+20), fill=color_main, width=5)
                    start_y += 60
                    for line in d_lines:
                        draw_text_with_stroke(draw, (150, start_y), line, font_body, fill="#cccccc", stroke_width=2)
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
        st.download_button("💾 카드뉴스 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_news_complete.zip", "application/zip", use_container_width=True)

    except Exception as e: st.error(f"이미지 생성 중 오류 발생: {e}")
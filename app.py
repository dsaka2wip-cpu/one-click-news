import streamlit as st
import google.generativeai as genai
from newspaper import Article, Config
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageColor, ImageOps, ImageStat
import io
import random
import zipfile
import qrcode
import os
import numpy as np
import fitz
import re

# --- [1] 페이지 설정 ---
st.set_page_config(page_title="One-Click News v13.6", page_icon="📰", layout="wide")

# --- [2] 고정 자산 ---
LOGO_SYMBOL_PATH = "segye_symbol.png"
LOGO_TEXT_PATH = "segye_text.png"

# ==============================================================================
# [3] 유틸리티 함수
# ==============================================================================

def extract_tag_from_title(title):
    match = re.search(r'\[(.*?)\]', title)
    if match:
        tag = match.group(1)
        clean_title = title.replace(f"[{tag}]", "").strip()
        return tag, clean_title
    return None, title

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
    
    valid_images = []
    if top_image: valid_images.append(top_image)
    for img_url in raw_images:
        if img_url == top_image: continue
        if 'icon' in img_url or 'logo' in img_url or 'banner' in img_url: continue
        valid_images.append(img_url)

    tag, clean_title = extract_tag_from_title(title)
    return tag, clean_title, text, valid_images

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

def recolor_image_to_white(pil_img):
    try:
        r, g, b, a = pil_img.split()
        white = Image.new('L', pil_img.size, 255)
        new_img = Image.merge('RGBA', (white, white, white, a))
        return new_img
    except: return pil_img

def check_brightness(img, box):
    try:
        crop = img.crop(box).convert('L')
        stat = ImageStat.Stat(crop)
        return stat.mean[0]
    except: return 128

def get_dominant_color(pil_img):
    try:
        img = pil_img.copy().convert("P", palette=Image.ADAPTIVE, colors=1)
        c = img.getpalette()[:3]
        return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
    except: return "#FFD700"

def get_available_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        return models[0] if models else "models/gemini-pro"
    except: return "models/gemini-pro"

def clean_text_spacing(text):
    if not text: return ""
    text = re.sub(r'\s*\.\s*', '.', text)
    text = re.sub(r'\s*\,', ',', text)
    return text.strip()

def validate_hex_color(c):
    match = re.search(r'#(?:[0-9a-fA-F]{3}){1,2}', str(c))
    return match.group(0) if match else "#FFD700"

def create_smooth_gradient(w, h):
    overlay = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    for y in range(h):
        ratio = y/h
        if ratio > 0.3:
            alpha = int(255 * ((ratio-0.3)/0.7)**1.5)
            draw.line([(0,y), (w,y)], fill=(0,0,0,alpha))
    return overlay

def draw_text_with_stroke(draw, pos, text, font, fill="white", stroke_fill="black", stroke_width=2):
    draw.text(pos, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)

# [수정] 뱃지 위치 정교화 및 디자인 개선
def draw_pill_badge(draw, x, y, text, font, bg_color="#C80000"):
    padding_x, padding_y = 15, 6
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    h = text_h + padding_y * 2
    w = text_w + padding_x * 2
    
    # 알약 모양
    draw.ellipse((x, y, x+h, y+h), fill=bg_color) 
    draw.ellipse((x+w-h, y, x+w, y+h), fill=bg_color)
    draw.rectangle((x+h//2, y, x+w-h//2, y+h), fill=bg_color)
    
    # 텍스트 중앙 보정
    draw.text((x + padding_x, y + padding_y - 2), text, font=font, fill="white")

def wrap_text(text, font, max_width, draw):
    lines = []
    text = clean_text_spacing(text)
    if not text: return []
    for para in text.split('\n'):
        if not para.strip(): continue
        words = para.split(' ')
        curr = words[0]
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
    return qr.make_image(fill_color="black", back_color="white").convert("RGBA")

# 로고 배치 및 뱃지 기준점 반환
def paste_logo_smart(bg_img, symbol, logotxt, x=50, y=50):
    check_area = (x, y, x+300, y+100)
    brightness = check_brightness(bg_img, check_area)
    use_white = brightness < 100
    
    next_x = x
    logo_height = 0
    
    if symbol:
        sym_to_paste = recolor_image_to_white(symbol) if use_white else symbol
        bg_img.paste(sym_to_paste, (x, y), sym_to_paste)
        next_x += symbol.width + 15
        logo_height = max(logo_height, symbol.height)
    
    if logotxt:
        txt_to_paste = recolor_image_to_white(logotxt) if use_white else logotxt
        # 텍스트 로고 수직 중앙 정렬
        target_y = y + (symbol.height - logotxt.height) // 2 if symbol else y
        bg_img.paste(txt_to_paste, (next_x, target_y), txt_to_paste)
        next_x += logotxt.width
        logo_height = max(logo_height, logotxt.height)
        
    return next_x, logo_height

def draw_rounded_box(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)

# ==============================================================================
# [4] 메인 UI
# ==============================================================================
st.title("📰 One-Click News (v13.6 Ultimate Integrity)")

# 1. URL 입력
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

# 2. 실행 버튼
run_button = st.button("🚀 카드뉴스 제작")

# 3. 결과 컨테이너 (여기에 카드가 뜸)
result_container = st.container()

# 4. [필독] 상세 안내문 (항상 펼침, 전체 히스토리 포함)
st.markdown("---")
with st.expander("💡 [안내] 세계일보 AI 카드뉴스 생성기: 기술 명세 및 가이드 (Full Ver.)", expanded=True):
    st.markdown("""
    ### 📌 프로젝트 개요
    이 도구는 단순한 텍스트 요약기가 아닙니다. **세계일보의 저널리즘 원칙**과 **최신 생성형 AI(Gemini Pro)** 기술을 결합하여, 기사의 맥락을 완벽하게 이해하고 시각화하는 **'지능형 콘텐츠 파트너'**입니다.

    ---

    ### 🧠 1. Intelligence (맥락 인식 및 기획)
    * **내러티브 구조화 (Narrative Arc):** 기계적인 요약을 거부합니다. 기사를 **'Hook(도입) - Content(전개) - Conclusion(결론)'**의 8단 서사 구조로 재구성하여 독자의 몰입을 유도합니다.
    * **맥락 기반 레이아웃 결정 (Context-Aware Design):** AI가 문단의 성격을 스스로 분석합니다.
        * **인용(Quote):** 인터뷰나 핵심 발언이 나오면 따옴표 디자인 적용.
        * **데이터(Data):** 숫자나 통계가 핵심이면 인포그래픽(Big Number) 디자인 적용.
        * **요약(Bar) / 서술(Box):** 내용의 호흡에 따라 최적의 레이아웃을 자동 선택합니다.
    * **태그 자동 감지 (Smart Tagging):** 기사 제목의 `[단독]`, `[심층기획]` 등을 자동으로 인식하여, 로고 옆에 **전용 뱃지**를 부착합니다.

    ### 🎨 2. Design Engine (미학적 완성도)
    * **스마트 디밍 (Smart Dimming):** 배경 사진이 밝아도 흰색 글씨가 선명하게 보이도록, 이미지의 밝기를 자동으로 낮추고 텍스트에 **Deep Shadow & Stroke** 기술을 적용했습니다.
    * **카멜레온 로고 (Adaptive Logo):** 배경이 어두우면 로고를 흰색으로, 밝으면 검은색으로 자동 변환하여 시인성을 확보합니다.
    * **안전형 레이아웃 (Safe Layout):** 텍스트가 카드 밖으로 잘리지 않도록 **Top-Down** 방식의 배치 로직과 넉넉한 여백(Padding)을 적용했습니다.
    * **멀티 포맷 지원:** 하나의 기사로 **인스타그램 피드(1:1)**와 **스토리/릴스(9:16)** 규격을 자유롭게 오갈 수 있습니다.

    ### 🛡️ 3. Core Tech (안정성 및 편의성)
    * **자동 자산 로드:** 로고와 전용 폰트를 서버에 내장하여, 매번 파일을 업로드하는 불편함을 없앴습니다.
    * **멀티 이미지 스크래핑:** 기사 썸네일뿐만 아니라 본문의 모든 이미지를 수집하여, 슬라이드마다 다채로운 배경을 제공합니다.
    * **Visual SEO:** 인스타그램 유입을 극대화하기 위해 기사 내용에 최적화된 **해시태그**를 자동 생성합니다.
    * **타이포그래피 자동 교정:** `3 . 1절`과 같은 어색한 띄어쓰기를 정규표현식 엔진이 자동으로 교정합니다.
    """)

# ==============================================================================
# [5] 사이드바
# ==============================================================================
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")
    format_option = st.radio("사이즈:", ["카드뉴스 (1:1)", "인스타 스토리 (9:16)"])
    CANVAS_W, CANVAS_H = (1080, 1920) if "9:16" in format_option else (1080, 1080)
    is_story = "9:16" in format_option
    st.markdown("---")
    user_image = st.file_uploader("대표 이미지 (선택)", type=['png','jpg','jpeg'])
    use_auto_color = st.checkbox("테마 색상 자동 추출", value=True)
    if os.path.exists(LOGO_SYMBOL_PATH): st.success("✅ 로고 시스템 준비됨")

# ==============================================================================
# [6] 실행 로직
# ==============================================================================
if run_button:
    with result_container:
        if not api_key: st.error("API Key 필요"); st.stop()
        if not url: st.error("URL 필요"); st.stop()
        
        status = st.empty()
        status.info("📰 기사 분석 중...")
        
        news_tag, title, text, scraped_images = advanced_scrape(url)
        if len(text) < 50: st.error("본문 추출 실패"); st.stop()

        # --- AI 기획 ---
        try:
            model_name = get_available_model()
            model = genai.GenerativeModel(model_name)
            
            prompt = f"""
            당신은 세계일보 전문 에디터이자 아트 디렉터입니다. 기사를 SNS용 카드뉴스 8장으로 기획하세요.
            [제목] {title}
            [내용] {text[:4000]}
            
            [레이아웃 결정 규칙]
            1. **TYPE: QUOTE** (인용/발언)
            2. **TYPE: DATA** (숫자/통계)
            3. **TYPE: BAR** (요약/명제)
            4. **TYPE: BOX** (일반 서술)
            
            [필수 규칙]
            1. **SLIDE 1 (COVER):** HEAD는 15자 이내 훅, DESC는 40자 이내.
            2. **SLIDE 2~7 (CONTENT):** 각 장의 DESC(본문)는 **80자 내외로 작성**. (절대 길게 쓰지 말 것, 박스 넘침 방지)
            3. **SLIDE 8 (OUTRO):** 고정.
            4. 해시태그 5개 추천.
            
            [출력형식]
            COLOR_MAIN: #Hex
            HASHTAGS: #태그
            
            [SLIDE 1]
            TYPE: COVER
            HEAD: ...
            DESC: ...
            ...
            """
            
            response = model.generate_content(prompt)
            res_text = response.text
            
            slides = []
            curr = {}
            ai_color = "#FFD700"
            hashtags = ""
            
            lines = res_text.split('\n')
            mode = None
            for line in lines:
                line = line.strip()
                if not line: continue
                if line.startswith("COLOR_MAIN:"): ai_color = validate_hex_color(line.split(":")[1])
                elif line.startswith("HASHTAGS:"): hashtags = line.split(":", 1)[1].strip()
                elif "[SLIDE" in line:
                    if curr: slides.append(curr)
                    curr = {"HEAD":"", "DESC":"", "TYPE":"BOX"}
                    mode = None
                elif line.startswith("TYPE:"): curr["TYPE"] = line.split(":", 1)[1].strip()
                elif line.startswith("HEAD:"): 
                    curr["HEAD"] = line.split(":", 1)[1].strip()
                    mode = "HEAD"
                elif line.startswith("DESC:"): 
                    curr["DESC"] = line.split(":", 1)[1].strip()
                    mode = "DESC"
                else:
                    if mode == "DESC" and curr: curr["DESC"] += " " + line
                    elif mode == "HEAD" and curr: curr["HEAD"] += " " + line
            if curr: slides.append(curr)
            
            if not slides: st.error("AI 생성 실패."); st.stop()
            
            if len(slides) >= 8: slides[7] = {"TYPE": "OUTRO", "HEAD":"", "DESC":""}
            while len(slides) < 8:
                 slides.append({"TYPE": "OUTRO" if len(slides)==7 else "BOX", "HEAD":"제목 없음", "DESC":"내용 없음"})

        except Exception as e: st.error(f"AI 오류: {e}"); st.stop()

        # --- 렌더링 ---
        status.info("🎨 이미지 생성 중...")
        try:
            font_paths = load_fonts_local()
            def safe_font(path, size):
                try: return ImageFont.truetype(path, size)
                except: return ImageFont.load_default()

            f_title = safe_font(font_paths['title'], 95)
            f_body = safe_font(font_paths['body'], 48)
            f_small = safe_font(font_paths['body'], 30)
            f_serif = safe_font(font_paths['serif'], 90)
            f_huge = safe_font(font_paths['title'], 200)
            f_badge = safe_font(font_paths['title'], 35)
            f_quote = safe_font(font_paths['serif'], 250)
            
            img_sym = load_local_image(LOGO_SYMBOL_PATH, 60)
            img_txt = load_local_image(LOGO_TEXT_PATH, 160)
            
            img_pool = []
            if user_image: img_pool.append(Image.open(io.BytesIO(user_image.getvalue())).convert('RGB'))
            else:
                for link in scraped_images:
                    try:
                        r = requests.get(link, timeout=2)
                        im = Image.open(io.BytesIO(r.content)).convert('RGB')
                        if im.width >= 300: img_pool.append(im)
                        if len(img_pool)>=5: break
                    except: continue
            if not img_pool: img_pool.append(Image.new('RGB', (1080, 1080), '#333'))

            color_main = get_dominant_color(img_pool[0]) if use_auto_color else ai_color
            bg_outro = Image.new('RGB', (CANVAS_W, CANVAS_H), color_main)
            
            generated_images = []
            tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
            
            for i, slide in enumerate(slides):
                sType = slide.get('TYPE', 'BOX').upper()
                
                # 배경
                if sType == 'OUTRO': img = bg_outro.copy()
                else:
                    base = img_pool[i % len(img_pool)].copy().resize((CANVAS_W, CANVAS_H))
                    if sType == 'COVER':
                        img = ImageEnhance.Brightness(base).enhance(0.7)
                        grad = create_smooth_gradient(CANVAS_W, CANVAS_H)
                        img.paste(grad, (0,0), grad)
                    else:
                        img = base.filter(ImageFilter.GaussianBlur(20))
                        img = ImageEnhance.Brightness(img).enhance(0.3)

                draw = ImageDraw.Draw(img, 'RGBA')
                
                # 상단 로고 & 뱃지
                top_y = 100 if is_story else 60
                if sType != 'OUTRO':
                    next_x = 60
                    logo_height = 40 # 기본값
                    
                    if img_sym or img_txt:
                        next_x, logo_height = paste_logo_smart(img, img_sym, img_txt, x=60, y=top_y)
                        next_x += 25
                    else:
                        draw.text((60, top_y), "SEGYE BRIEFING", font=f_small, fill=color_main)
                        next_x = 320

                    if news_tag:
                        # 뱃지 높이(약 50px)를 고려하여 로고 중앙에 맞춤
                        badge_y = top_y + (logo_height // 2) - 25 
                        draw_pill_badge(draw, next_x, badge_y, news_tag, f_badge, bg_color="#C80000")
                    
                    draw_text_with_stroke(draw, (CANVAS_W-130, top_y), f"{i+1}/{len(slides)}", f_small)

                # 내용 그리기 (여백 120px 확보)
                head = clean_text_spacing(slide.get('HEAD', ''))
                desc = clean_text_spacing(slide.get('DESC', ''))
                content_width = CANVAS_W - 240 # 좌우 120씩 여백
                
                if sType == 'COVER':
                    d_lines = wrap_text(desc, f_body, content_width, draw)
                    curr_y = CANVAS_H - 150 - (len(d_lines)*60)
                    for l in d_lines:
                        draw_text_with_stroke(draw, (60, curr_y), l, f_body, stroke_width=2)
                        curr_y += 60
                    curr_y -= (len(d_lines)*60 + 40)
                    draw.rectangle([(60, curr_y), (160, curr_y+10)], fill=color_main)
                    h_lines = wrap_text(head, f_title, content_width, draw)
                    curr_y -= (len(h_lines)*110 + 20)
                    for l in h_lines:
                        draw_text_with_stroke(draw, (60, curr_y), l, f_title, stroke_width=3)
                        curr_y += 110

                elif sType == 'DATA':
                    bbox = draw.textbbox((0,0), head, font=f_huge)
                    w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
                    draw_text_with_stroke(draw, ((CANVAS_W-w)//2, (CANVAS_H-h)//2 - 100), head, f_huge, fill=color_main, stroke_width=4)
                    d_lines = wrap_text(desc, f_body, 800, draw)
                    curr_y = (CANVAS_H//2) + 100
                    for l in d_lines:
                        lw = draw.textlength(l, font=f_body)
                        draw_text_with_stroke(draw, ((CANVAS_W-lw)//2, curr_y), l, f_body, stroke_width=2)
                        curr_y += 60

                elif sType == 'QUOTE':
                    start_y = 250 if not is_story else 350
                    draw.text((80, start_y - 120), "“", font=f_quote, fill=(255,255,255,70))
                    h_lines = wrap_text(head, f_title, content_width, draw)
                    for l in h_lines:
                        draw_text_with_stroke(draw, (150, start_y), l, f_title, stroke_width=3)
                        start_y += 110
                    draw.line((150, start_y+20, 350, start_y+20), fill=color_main, width=5)
                    start_y += 60
                    d_lines = wrap_text(desc, f_body, content_width, draw)
                    for l in d_lines:
                        draw_text_with_stroke(draw, (150, start_y), l, f_body, stroke_width=2)
                        start_y += 65

                elif sType == 'BAR':
                    start_y = 250 if not is_story else 350
                    h_lines = wrap_text(head, f_title, content_width, draw)
                    d_lines = wrap_text(desc, f_body, content_width, draw)
                    total_h = (len(h_lines)*110) + (len(d_lines)*65) + 60
                    draw.rectangle([(80, start_y), (95, start_y + total_h)], fill=color_main)
                    
                    for l in h_lines:
                        draw_text_with_stroke(draw, (120, start_y), l, f_title, stroke_width=3)
                        start_y += 110
                    start_y += 30
                    for l in d_lines:
                        draw_text_with_stroke(draw, (120, start_y), l, f_body, stroke_width=2)
                        start_y += 65

                elif sType == 'OUTRO':
                    out_c = "white" if is_color_dark(color_main) else "black"
                    slogan = "First in, Last out"
                    w = draw.textlength(slogan, font=f_serif)
                    draw.text(((CANVAS_W-w)/2, CANVAS_H//3), slogan, font=f_serif, fill=out_c)
                    brand = "세상을 보는 눈, 세계일보"
                    w2 = draw.textlength(brand, font=f_body)
                    draw.text(((CANVAS_W-w2)/2, CANVAS_H//3 + 130), brand, font=f_body, fill=out_c)
                    qr = generate_qr_code(url).resize((250, 250))
                    qx, qy = (CANVAS_W-250)//2, CANVAS_H//3 + 300
                    draw.rounded_rectangle((qx, qy, qx+250, qy+250), 20, "white")
                    img.paste(qr, (qx+10, qy+10), qr) # Mask 사용
                    msg = "기사 원문 보러가기"
                    w3 = draw.textlength(msg, font=f_small)
                    draw.text(((CANVAS_W-w3)/2, qy + 270), msg, font=f_small, fill=out_c)

                else: # BOX
                    start_y = 250 if not is_story else 350
                    h_lines = wrap_text(head, f_title, content_width, draw)
                    d_lines = wrap_text(desc, f_body, content_width, draw)
                    
                    box_h = (len(h_lines)*110) + (len(d_lines)*65) + 120
                    box_start_y = max(start_y, (CANVAS_H - box_h) // 2)
                    draw_rounded_box(draw, (80, box_start_y, CANVAS_W-80, box_start_y + box_h), 30, (0,0,0,160))
                    txt_y = box_start_y + 50
                    
                    for l in h_lines:
                        draw_text_with_stroke(draw, (120, txt_y), l, f_title, fill=color_main, stroke_width=0)
                        txt_y += 110
                    draw.line((120, txt_y+10, 320, txt_y+10), fill=color_main, width=5)
                    txt_y += 40
                    for l in d_lines:
                        draw_text_with_stroke(draw, (120, txt_y), l, f_body, fill="white", stroke_width=0)
                        txt_y += 65

                generated_images.append(img)
                with tabs[i]: st.image(img)

            # 다운로드
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for i, img in enumerate(generated_images):
                    ib = io.BytesIO()
                    img.save(ib, format='PNG')
                    zf.writestr(f"card_{i+1:02d}.png", ib.getvalue())
            
            st.success("✅ 제작 완료! 해시태그를 복사해서 쓰세요.")
            st.code(hashtags, language="text")
            st.download_button("💾 다운로드", zip_buf.getvalue(), "segye_news.zip", "application/zip", use_container_width=True)

        except Exception as e: st.error(f"오류 발생: {e}")
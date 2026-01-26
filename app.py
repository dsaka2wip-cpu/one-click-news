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
st.set_page_config(page_title="One-Click News v12.5", page_icon="📰", layout="wide")

# --- [2] 고정 자산 설정 ---
LOGO_SYMBOL_PATH = "segye_symbol.png"
LOGO_TEXT_PATH = "segye_text.png"

# ==============================================================================
# [3] 함수 정의 구역
# ==============================================================================

# 3-1. 태그 추출 및 스크래핑
def extract_tag_from_title(title):
    """제목에서 [단독], [기획] 같은 태그를 추출하고 제목에서 제거함"""
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
        title, text, top_image = article.title, article.text, article.top_image
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

    # [NEW] 태그 분리
    tag, clean_title = extract_tag_from_title(title)
            
    return tag, clean_title, text, valid_images

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

def draw_text_with_stroke(draw, position, text, font, fill="white", stroke_fill="black", stroke_width=2):
    draw.text(position, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)

# [NEW] 뱃지 그리기
def draw_badge(draw, x, y, text, font, bg_color="#D90000", text_color="white"):
    padding = 15
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    # 빨간 박스
    draw.rounded_rectangle(
        (x, y, x + text_w + padding*2, y + text_h + padding + 10),
        radius=10, fill=bg_color
    )
    # 글씨
    draw.text((x + padding, y + 2), text, font=font, fill=text_color)
    return x + text_w + padding*2 + 20 # 다음 요소 시작 X좌표 반환

def wrap_text(text, font, max_width, draw):
    lines = []
    text = clean_text_spacing(text)
    if not text: return []
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
    return next_x

# ==============================================================================
# [4] 메인 UI (순서: URL -> 버튼 -> 안내)
# ==============================================================================
st.title("📰 One-Click News (v12.5 Safe Layout)")

url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")
run_button = st.button("🚀 카드뉴스 제작")

with st.expander("💡 [안내] 세계일보 AI 카드뉴스 생성 원리 & 기능 명세", expanded=True):
    st.markdown("""
    ### 🧠 1. Intelligence (맥락 인식 기획)
    * **내러티브 구조화:** 'Hook(유입) - Content(전개) - Conclusion(결론)'의 8단 구성.
    * **데이터 감지 (Big Number):** 수치(%, 금액 등)가 감지되면 인포그래픽 슬라이드로 변환.
    * **[NEW] 태그 자동 감지:** 기사 제목의 [단독], [기획] 등을 인식해 뱃지로 표시.

    ### 🎨 2. Design Engine (유동적 디자인)
    * **멀티 포맷:** 인스타그램 피드(1:1) / 스토리(9:16) 지원.
    * **Auto Color:** 사진에서 가장 어울리는 테마 색상 자동 추출.
    * **[NEW] 안전형 레이아웃:** 텍스트가 절대 잘리지 않는 Top-Down 배치 방식 적용.

    ### 🛡️ 3. Core Tech & SEO
    * **자동 자산 로드:** 로고/폰트 서버 내장으로 깨짐 방지.
    * **Visual SEO:** 인스타그램 최적화 해시태그 자동 생성.
    * **Smart Dimming:** 배경 밝기 자동 조절로 가독성 확보.
    """)

st.markdown("---")

# ==============================================================================
# [5] 사이드바 설정
# ==============================================================================
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")
    format_option = st.radio("제작할 사이즈:", ["카드뉴스 (1:1)", "인스타 스토리 (9:16)"])
    if "9:16" in format_option: CANVAS_W, CANVAS_H, is_story = 1080, 1920, True
    else: CANVAS_W, CANVAS_H, is_story = 1080, 1080, False
    st.markdown("---")
    user_image = st.file_uploader("대표 이미지 (선택)", type=['png', 'jpg', 'jpeg'])
    use_auto_color = st.checkbox("📸 테마 색상 자동 추출", value=True)
    if os.path.exists(LOGO_SYMBOL_PATH): st.success("✅ 로고 로드 완료")

# ==============================================================================
# [6] 메인 실행 로직
# ==============================================================================
if run_button:
    if not api_key: st.error("API Key 필요"); st.stop()
    if not url: st.error("URL 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사 분석 중...")
    
    # [수정] 태그 추출 추가
    news_tag, title, text, scraped_images = advanced_scrape(url)
    
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- AI 기획 ---
    try:
        model_name = get_available_model()
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
        당신은 세계일보 에디터입니다. 기사를 카드뉴스 8장으로 기획하세요.
        [기사 제목] {title}
        [기사 내용] {text[:4000]}
        
        [규칙]
        1. **각 장의 DESC(본문)는 80자 이상 풍부하게 작성.** (비어있으면 절대 안 됨)
        2. 숫자가 핵심이면 TYPE: DATA.
        3. 마지막에 해시태그 5개.
        
        [출력]
        COLOR_MAIN: #Hex
        HASHTAGS: #태그
        [SLIDE 1]
        TYPE: COVER
        HEAD: (제목)
        DESC: (내용)
        ...
        """
        
        response = model.generate_content(prompt)
        res_text = response.text
        
        slides = []
        curr = {}
        ai_color = "#FFD700"
        hashtags = ""
        
        for line in res_text.split('\n'):
            line = line.strip()
            if not line: continue
            clean = line.replace('*', '').replace('#', '').strip()
            
            if "COLOR_MAIN" in clean: ai_color = validate_hex_color(clean.split(":")[1])
            elif "HASHTAGS" in clean: hashtags = clean.split(":", 1)[1].strip()
            elif "[SLIDE" in clean:
                if curr: slides.append(curr)
                curr = {"HEAD": "", "DESC": "", "TYPE": "CONTENT"}
            elif "TYPE:" in clean: curr["TYPE"] = clean.split(":", 1)[1].strip()
            elif "HEAD:" in clean: curr["HEAD"] = clean.split(":", 1)[1].strip()
            elif "DESC:" in clean: curr["DESC"] = clean.split(":", 1)[1].strip()
        if curr: slides.append(curr)
        
        # [Fail-safe] 내용 비었으면 원문에서 채우기
        if not slides: st.error("AI 응답 오류"); st.stop()
        for s in slides:
            if not s.get("DESC"): s["DESC"] = text[:100] + "..." # 비상 대책

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
        f_badge = safe_font(font_paths['body'], 35) # 뱃지용 폰트
        
        img_sym = load_local_image(LOGO_SYMBOL_PATH, 60)
        img_txt = load_local_image(LOGO_TEXT_PATH, 160)
        
        # 이미지 풀
        img_pool = []
        if user_image:
            img_pool.append(Image.open(io.BytesIO(user_image.getvalue())).convert('RGB'))
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
        
        layouts = ['BOX', 'BAR', 'QUOTE']
        
        for i, slide in enumerate(slides):
            sType = slide.get('TYPE', 'CONTENT')
            
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
                    img = ImageEnhance.Brightness(img).enhance(0.3) # 아주 어둡게

            draw = ImageDraw.Draw(img, 'RGBA')
            
            # 상단 로고 & 뱃지
            top_y = 100 if is_story else 60
            if sType != 'OUTRO':
                next_x = 60
                if img_sym or img_txt:
                    next_x = paste_hybrid_logo(img, img_sym, img_txt, x=60, y=top_y)
                else:
                    draw.text((60, top_y), "SEGYE BRIEFING", f_small, fill=color_main)
                    next_x = 300
                
                # [NEW] 뱃지 그리기 (로고 옆에)
                if news_tag:
                    draw_badge(draw, next_x + 10, top_y + 10, news_tag, f_badge)
                
                draw_text_with_stroke(draw, (CANVAS_W-130, top_y), f"{i+1}/{len(slides)}", f_small)

            # --- 내용 그리기 (Safe Layout 적용) ---
            head = clean_text_spacing(slide.get('HEAD', ''))
            desc = clean_text_spacing(slide.get('DESC', ''))
            
            # 1. COVER: 하단 고정
            if sType == 'COVER':
                d_lines = wrap_text(desc, f_body, CANVAS_W-100, draw)
                # 바닥에서 150px 띄우고 시작
                curr_y = CANVAS_H - 150 - (len(d_lines)*60)
                for l in d_lines:
                    draw_text_with_stroke(draw, (60, curr_y), l, f_body, stroke_width=2)
                    curr_y += 60
                
                curr_y -= (len(d_lines)*60 + 40)
                draw.rectangle([(60, curr_y), (160, curr_y+10)], fill=color_main)
                
                h_lines = wrap_text(head, f_title, CANVAS_W-100, draw)
                curr_y -= (len(h_lines)*110 + 20)
                for l in h_lines:
                    draw_text_with_stroke(draw, (60, curr_y), l, f_title, stroke_width=3)
                    curr_y += 110

            # 2. DATA (빅 넘버): 중앙
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

            # 3. CONTENT: 상단 고정 (Top-Down) -> 절대 안 잘림
            elif sType == 'CONTENT':
                # 무조건 위에서 250px 내려온 지점부터 그림
                start_y = 250 if not is_story else 350
                
                # 제목
                h_lines = wrap_text(head, f_title, CANVAS_W-120, draw)
                for l in h_lines:
                    draw_text_with_stroke(draw, (60, start_y), l, f_title, fill=color_main, stroke_width=2)
                    start_y += 110
                
                # 구분선
                draw.line((60, start_y, 200, start_y), fill="white", width=5)
                start_y += 50
                
                # 본문
                d_lines = wrap_text(desc, f_body, CANVAS_W-120, draw)
                for l in d_lines:
                    draw_text_with_stroke(draw, (60, start_y), l, f_body, fill="white", stroke_width=2)
                    start_y += 65

            # 4. OUTRO
            elif sType == 'OUTRO':
                out_c = "white" if is_color_dark(color_main) else "black"
                slogan = "First in, Last out"
                w = draw.textlength(slogan, font=f_serif)
                draw.text(((CANVAS_W-w)/2, CANVAS_H//3), slogan, f_serif, fill=out_c)
                
                qr = generate_qr_code(url).resize((250, 250))
                qx = (CANVAS_W-250)//2
                qy = CANVAS_H//2
                draw.rounded_rectangle((qx, qy, qx+250, qy+250), 20, "white")
                img.paste(qr, (qx+10, qy+10))

            generated_images.append(img)
            with tabs[i]: st.image(img)

        # 다운로드
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for i, img in enumerate(generated_images):
                ib = io.BytesIO()
                img.save(ib, format='PNG')
                zf.writestr(f"card_{i+1:02d}.png", ib.getvalue())
        
        st.success("✅ 완료! 해시태그 복사:")
        st.code(hashtags)
        st.download_button("💾 다운로드", zip_buf.getvalue(), "segye_news.zip", "application/zip", use_container_width=True)

    except Exception as e: st.error(f"오류: {e}")
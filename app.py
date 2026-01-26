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
import fitz
import re

# --- [1] 페이지 설정 ---
st.set_page_config(page_title="One-Click News v12.6 Hotfix", page_icon="📰", layout="wide")

# --- [2] 고정 자산 ---
LOGO_SYMBOL_PATH = "segye_symbol.png"
LOGO_TEXT_PATH = "segye_text.png"

# ==============================================================================
# [3] 함수 정의
# ==============================================================================

# 3-1. 태그 추출 및 스크래핑
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

    tag, clean_title = extract_tag_from_title(title)
    return tag, clean_title, text, valid_images

# 3-2. 자산 및 폰트 로더
@st.cache_resource
def get_web_resources(): return None # 미사용

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

# 3-3. 유틸리티
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

# 3-4. 드로잉 함수
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

# [수정] 뱃지 디자인 및 위치 계산 개선
def draw_badge(draw, x, y, text, font, bg_color="#D90000"):
    padding_x, padding_y = 15, 8
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    # 둥근 박스
    draw.rounded_rectangle((x, y, x + tw + padding_x*2, y + th + padding_y*2), radius=15, fill=bg_color)
    # 텍스트 중앙 정렬
    draw.text((x + padding_x, y + padding_y), text, font=font, fill="white")

def wrap_text(text, font, max_width, draw):
    lines = []
    text = clean_text_spacing(text)
    if not text: return []
    for para in text.split('\n'):
        if not para.strip(): continue
        words = para.split(' ')
        curr = words[0]
        for word in words[1:]:
            bbox = draw.textbbox((0,0), curr + " " + word, font=font)
            if bbox[2]-bbox[0] <= max_width: curr += " " + word
            else: lines.append(curr); curr = word
        lines.append(curr)
    return lines

def generate_qr_code(link):
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(link)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")

def is_color_dark(hex):
    hex = hex.lstrip('#')
    rgb = tuple(int(hex[i:i+2], 16) for i in (0,2,4))
    return (0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]) < 128

# [수정] 로고 다음 위치 반환하도록 변경
def paste_hybrid_logo(bg_img, symbol, logotxt, x=50, y=50, gap=15):
    next_x = x
    if symbol:
        bg_img.paste(symbol, (x, y), symbol)
        next_x += symbol.width + gap
    if logotxt:
        target_y = y
        if symbol: target_y = y + (symbol.height - logotxt.height) // 2
        bg_img.paste(logotxt, (next_x, target_y), logotxt)
        next_x += logotxt.width
    return next_x

# ==============================================================================
# [4] 메인 UI
# ==============================================================================
st.title("📰 One-Click News (v12.6 Critical Hotfix)")
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")
run_button = st.button("🚀 카드뉴스 제작")

with st.expander("💡 [안내] 기능 명세 (v12.6 수정판)", expanded=True):
    st.markdown("""
    * **[긴급수정] 뱃지 겹침 해결:** [단독] 태그가 로고를 가리지 않도록 위치를 자동 계산합니다.
    * **[긴급수정] 본문 실종 방지:** AI 오류 시 기사 원문을 강제로 삽입하여 빈 카드를 막습니다.
    * **[긴급수정] 아웃트로 강제:** 8번째 장은 무조건 QR/슬로건 페이지로 고정됩니다.
    * **[긴급수정] 커버 과부하 방지:** 1면은 짧고 강렬한 훅(Hook) 위주로 구성됩니다.
    """)
st.markdown("---")

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
    user_image = st.file_uploader("대표 이미지", type=['png','jpg','jpeg'])
    use_auto_color = st.checkbox("테마 색상 자동 추출", value=True)

# ==============================================================================
# [6] 실행 로직
# ==============================================================================
if run_button:
    if not api_key: st.error("API Key 필요"); st.stop()
    if not url: st.error("URL 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사 분석 중...")
    
    news_tag, title, text, scraped_images = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- AI 기획 (프롬프트 강화) ---
    try:
        model_name = get_available_model()
        model = genai.GenerativeModel(model_name)
        
        # [수정] 1면 훅 강화 & 나머지 내용 충실 지시
        prompt = f"""
        당신은 세계일보 에디터입니다. 기사를 8장 카드뉴스로 기획하세요.
        [제목] {title}
        [내용] {text[:4000]}
        
        [필수규칙]
        1. **SLIDE 1 (COVER):** HEAD는 15자 이내의 강렬한 훅, DESC는 40자 이내의 아주 짧은 요약. (정보 과부하 금지)
        2. **SLIDE 2~7 (CONTENT):** 각 DESC를 80자 이상 충실히 작성. 절대 비워두지 마시오.
        3. SLIDE 8 (OUTRO): 고정.
        4. 해시태그 5개.
        
        [출력형식]
        COLOR_MAIN: #Hex
        HASHTAGS: #태그
        [SLIDE 1]
        TYPE: COVER
        HEAD: (짧은 제목)
        DESC: (짧은 요약)
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
        
        # [핵심 수정] Fail-safe & Outro 강제
        if not slides: st.error("AI 오류"); st.stop()
        
        # 1. 내용 비었으면 원문 강제 주입
        paragraphs = text.split('\n')
        para_idx = 0
        for i, s in enumerate(slides):
            if i < 7 and (not s.get("DESC") or len(s.get("DESC")) < 10):
                filler = ""
                while len(filler) < 80 and para_idx < len(paragraphs):
                    filler += paragraphs[para_idx] + " "
                    para_idx += 1
                s["DESC"] = filler[:150] if filler else "내용을 불러올 수 없습니다."
        
        # 2. 8번째 장은 무조건 아웃트로
        if len(slides) >= 8:
            slides[7] = {"TYPE": "OUTRO", "HEAD": "", "DESC": ""}
        while len(slides) < 8: # 부족하면 채움
             slides.append({"TYPE": "OUTRO" if len(slides)==7 else "CONTENT", "HEAD":"", "DESC":""})

    except Exception as e: st.error(f"AI 기획 실패: {e}"); st.stop()

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
        f_badge = safe_font(font_paths['body'], 30)
        
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
                    img = ImageEnhance.Brightness(img).enhance(0.3)

            draw = ImageDraw.Draw(img, 'RGBA')
            
            # [핵심 수정] 상단 로고 & 뱃지 위치 계산
            top_y = 100 if is_story else 60
            if sType != 'OUTRO':
                next_x = 60
                if img_sym or img_txt:
                    # 로고 그리고 다음 위치 받아옴
                    next_x = paste_hybrid_logo(img, img_sym, img_txt, x=60, y=top_y)
                    next_x += 25 # 로고 옆 간격
                else:
                    draw.text((60, top_y), "SEGYE BRIEFING", f_small, fill=color_main)
                    next_x = 320 # 텍스트 대략적 끝 위치

                # 뱃지 그리기 (계산된 위치에)
                if news_tag:
                    draw_badge(draw, next_x, top_y - 5, news_tag, f_badge) # y위치 살짝 조정
                
                draw_text_with_stroke(draw, (CANVAS_W-130, top_y), f"{i+1}/{len(slides)}", f_small)

            # 내용 그리기
            head = clean_text_spacing(slide.get('HEAD', ''))
            desc = clean_text_spacing(slide.get('DESC', ''))
            
            if sType == 'COVER': # [수정] 훅(Hook) 중심으로 간결하게
                d_lines = wrap_text(desc, f_body, CANVAS_W-100, draw)
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

            elif sType == 'CONTENT':
                start_y = 250 if not is_story else 350
                h_lines = wrap_text(head, f_title, CANVAS_W-120, draw)
                for l in h_lines:
                    draw_text_with_stroke(draw, (60, start_y), l, f_title, fill=color_main, stroke_width=2)
                    start_y += 110
                draw.line((60, start_y, 200, start_y), fill="white", width=5)
                start_y += 50
                d_lines = wrap_text(desc, f_body, CANVAS_W-120, draw)
                for l in d_lines:
                    draw_text_with_stroke(draw, (60, start_y), l, f_body, fill="white", stroke_width=2)
                    start_y += 65

            elif sType == 'OUTRO': # [수정] 강제 적용됨
                out_c = "white" if is_color_dark(color_main) else "black"
                slogan = "First in, Last out"
                w = draw.textlength(slogan, font=f_serif)
                draw.text(((CANVAS_W-w)/2, CANVAS_H//3), slogan, f_serif, fill=out_c)
                brand = "세상을 보는 눈, 세계일보"
                w2 = draw.textlength(brand, font=f_body)
                draw.text(((CANVAS_W-w2)/2, CANVAS_H//3 + 130), brand, f_body, fill=out_c)
                qr = generate_qr_code(url).resize((250, 250))
                qx, qy = (CANVAS_W-250)//2, CANVAS_H//3 + 300
                draw.rounded_rectangle((qx, qy, qx+250, qy+250), 20, "white")
                img.paste(qr, (qx+10, qy+10))
                msg = "기사 원문 보러가기"
                w3 = draw.textlength(msg, font=f_small)
                draw.text(((CANVAS_W-w3)/2, qy + 270), msg, f_small, fill=out_c)

            generated_images.append(img)
            with tabs[i]: st.image(img)

        # 다운로드
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for i, img in enumerate(generated_images):
                ib = io.BytesIO()
                img.save(ib, format='PNG')
                zf.writestr(f"card_{i+1:02d}.png", ib.getvalue())
        
        st.success("✅ 제작 완료! (v12.6 Hotfix applied)")
        st.code(hashtags)
        st.download_button("💾 다운로드", zip_buf.getvalue(), "segye_news.zip", "application/zip", use_container_width=True)

    except Exception as e: st.error(f"오류 발생: {e}")
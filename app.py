import streamlit as st
import google.generativeai as genai
from newspaper import Article, Config
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageStat
import fitz  # PyMuPDF
from io import BytesIO
import re
import random
import zipfile
import qrcode
from datetime import datetime
import numpy as np

# --- 페이지 설정 ---
st.set_page_config(page_title="One-Click News v8.0", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v8.1 Segae Identity)")
st.markdown("### 💎 세계일보 CI & 글씨체 적용 (에러 수정판)")

# --- 리소스 캐싱 ---
@st.cache_resource
def get_resources():
    resources = {}
    try:
        # 1. 폰트 (Google Fonts에서 유사 폰트 로드)
        resources['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf", timeout=10).content
        resources['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        resources['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return resources

# --- 디자인 유틸리티 ---
def add_noise_texture(img, intensity=0.05):
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    width, height = img.size
    noise = np.random.randint(0, 255, (height, width, 4), dtype=np.uint8)
    noise[:, :, 3] = int(255 * intensity)
    noise_img = Image.fromarray(noise, 'RGBA')
    return Image.alpha_composite(img, noise_img)

def draw_rounded_box(draw, xy, r, fill):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1, y1, x2, y2), radius=r, fill=fill)

def create_smooth_gradient(width, height):
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        ratio = y / height
        if ratio > 0.4:
            alpha = int(255 * ((ratio - 0.4) / 0.6) ** 2) 
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return overlay

def draw_text_safe(draw, text, font, x, y, color="white"):
    stroke_width = 3
    stroke_color = "black"
    draw.text((x-stroke_width, y), text, font=font, fill=stroke_color)
    draw.text((x+stroke_width, y), text, font=font, fill=stroke_color)
    draw.text((x, y-stroke_width), text, font=font, fill=stroke_color)
    draw.text((x, y+stroke_width), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=color)
    
def draw_text_with_shadow(draw, position, text, font, fill="white", shadow_color="black", offset=(2, 2)):
    x, y = position
    draw.text((x + offset[0], y + offset[1]), text, font=font, fill=shadow_color)
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

def render_ai_to_image(ai_bytes):
    try:
        doc = fitz.open(stream=ai_bytes, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=True)
        return Image.open(BytesIO(pix.tobytes("png"))).convert("RGBA")
    except:
        return None

def render_font_preview(font_bytes, text, size=32, width=520, height=80):
    try:
        img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(BytesIO(font_bytes), size)
        draw.text((10, 18), text, font=font, fill="#111111")
        return img
    except:
        return None

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
    if len(text) < 50:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            if not title: title = soup.find('title').text.strip()
            if not top_image:
                meta = soup.find('meta', property='og:image')
                if meta: top_image = meta['content']
            if len(text) < 50: text = soup.get_text(separator=' ', strip=True)[:5000] 
        except: pass
    return title, text, top_image

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")
    user_image = st.file_uploader("기사 사진 업로드 (1순위)", type=['png', 'jpg', 'jpeg'])
    logo_files = st.file_uploader("세계일보 로고/CI (PNG/JPG/AI)", type=['png', 'jpg', 'jpeg', 'ai'], accept_multiple_files=True)
    title_font_files = st.file_uploader("제목 폰트 업로드 (TTF/OTF)", type=['ttf', 'otf'], accept_multiple_files=True)
    body_font_files = st.file_uploader("본문 폰트 업로드 (TTF/OTF)", type=['ttf', 'otf'], accept_multiple_files=True)
    serif_font_files = st.file_uploader("명조 폰트 업로드 (TTF/OTF)", type=['ttf', 'otf'], accept_multiple_files=True)

    selected_logo_file = None
    if logo_files:
        logo_names = [f.name for f in logo_files]
        selected_logo_name = st.selectbox("사용할 CI 선택", logo_names)
        selected_logo_file = next((f for f in logo_files if f.name == selected_logo_name), None)

    title_font_options = ["기본(BlackHanSans)"]
    if title_font_files:
        title_font_options += [f.name for f in title_font_files]
    selected_title_font_name = st.selectbox("제목 폰트 선택", title_font_options)
    selected_title_font_file = None
    if selected_title_font_name != title_font_options[0] and title_font_files:
        selected_title_font_file = next((f for f in title_font_files if f.name == selected_title_font_name), None)

    body_font_options = ["기본(NanumGothic-Bold)"]
    if body_font_files:
        body_font_options += [f.name for f in body_font_files]
    selected_font_name = st.selectbox("본문 폰트 선택", body_font_options)
    selected_font_file = None
    if selected_font_name != body_font_options[0] and body_font_files:
        selected_font_file = next((f for f in body_font_files if f.name == selected_font_name), None)

    serif_font_options = ["기본(NanumMyeongjo-ExtraBold)"]
    if serif_font_files:
        serif_font_options += [f.name for f in serif_font_files]
    selected_serif_font_name = st.selectbox("명조 폰트 선택", serif_font_options)
    selected_serif_font_file = None
    if selected_serif_font_name != serif_font_options[0] and serif_font_files:
        selected_serif_font_file = next((f for f in serif_font_files if f.name == selected_serif_font_name), None)

    # Font previews
    try:
        res_cache = get_resources()
        title_preview_bytes = selected_title_font_file.getvalue() if selected_title_font_file else res_cache['title']
        body_preview_bytes = selected_font_file.getvalue() if selected_font_file else res_cache['body']
        serif_preview_bytes = selected_serif_font_file.getvalue() if selected_serif_font_file else res_cache['serif']

        st.markdown("#### 폰트 미리보기")
        title_preview = render_font_preview(title_preview_bytes, "제목 미리보기: 세계일보", size=34)
        body_preview = render_font_preview(body_preview_bytes, "본문 미리보기: 세상을 보는 눈", size=28)
        serif_preview = render_font_preview(serif_preview_bytes, "명조 미리보기: First in, Last out", size=30)

        if title_preview: st.image(title_preview, use_container_width=True)
        if body_preview: st.image(body_preview, use_container_width=True)
        if serif_preview: st.image(serif_preview, use_container_width=True)
    except:
        st.caption("폰트 리소스를 불러오는 중입니다...")

# --- 메인 ---
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

if st.button("🚀 세계일보 카드뉴스 제작"):
    if not api_key or not url: st.error("설정 확인 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사 분석 및 디자인 적용 중...")
    
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- AI 프롬프트 ---
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        prompt = f"""
        당신은 세계일보의 '디지털 스토리텔링 에디터'입니다.
        
        [기사]
        제목: {title}
        내용: {text[:6000]}
        
        [규칙]
        1. **총 8장 (Cover 1 + Story 6 + Outro 1)**
        2. **Cover:** - HEAD: 10자 이내 임팩트 (예: "킹메이커의 퇴장")
           - DESC: 40자 이내 부제
        3. **Story (2~7p):** - HEAD: 핵심 키워드
           - DESC: **80~100자 내외**의 구체적 서술. (빈약하면 안 됨)
           - 앞 내용 반복 금지. 시간 순서나 사건 중심으로 전개.
        4. **Color:** 기사 분위기에 맞는 짙은 색상(Hex) 1개.
        
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
        [SLIDE 8]
        TYPE: OUTRO
        HEAD: First in, Last out
        DESC: 세상을 보는 눈, 세계일보
        """
        response = model.generate_content(prompt)
        res_text = response.text
        
        slides = []
        current_slide = {}
        color_main = "#FFD700"
        
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

    # --- 이미지 및 로고 준비 ---
    try:
        # 1. 메인 이미지
        if user_image: base_img = Image.open(user_image)
        elif img_url:
            headers = {'User-Agent': 'Mozilla/5.0'}
            base_img = Image.open(BytesIO(requests.get(img_url, headers=headers, timeout=5).content))
        else: base_img = Image.new('RGB', (1080, 1080), color='#1a1a2e')
        base_img = base_img.convert('RGB').resize((1080, 1080))
        
        # 2. Cover용 (선명 + 부드러운 그라데이션)
        bg_cover = base_img.copy()
        grad = create_smooth_gradient(1080, 1080)
        bg_cover.paste(grad, (0,0), grad)
        
        # 3. Content용 (블러 + 살짝 어둡게)
        bg_blur = base_img.copy()
        bg_blur = bg_blur.filter(ImageFilter.GaussianBlur(15)) # 블러 적당히
        bg_blur = ImageEnhance.Brightness(bg_blur).enhance(0.7)
        
        # 4. Outro용 (단색 + 노이즈)
        try: bg_outro = Image.new('RGB', (1080, 1080), color=color_main)
        except: bg_outro = Image.new('RGB', (1080, 1080), color='#1a1a2e')
        bg_outro = add_noise_texture(bg_outro, 0.03)

        # 5. 로고 준비
        logo_img = None
        if selected_logo_file:
            data = selected_logo_file.getvalue()
            if selected_logo_file.name.lower().endswith('.ai'):
                logo_img = render_ai_to_image(data)
            else:
                logo_img = Image.open(BytesIO(data)).convert("RGBA")
            if logo_img:
                ar = logo_img.height / logo_img.width
                logo_img = logo_img.resize((280, int(280*ar)))
            else:
                st.warning("로고 파일 변환 실패")
        
        # 6. 폰트 준비 (핵심 수정: 바이트로 로드)
        res_cache = get_resources()
        if not res_cache: st.error("폰트 리소스 다운로드 실패"); st.stop()

        def load_font_bytes(file_obj, default_bytes):
            if file_obj: return file_obj.getvalue() # BytesIO가 아닌 bytes 반환
            return default_bytes

        title_font_bytes = load_font_bytes(selected_title_font_file, res_cache['title'])
        body_font_bytes = load_font_bytes(selected_font_file, res_cache['body'])
        serif_font_bytes = load_font_bytes(selected_serif_font_file, res_cache['serif'])
            
    except Exception as e: st.error(f"이미지/리소스 처리 실패: {e}"); st.stop()

    # --- 렌더링 루프 ---
    st.markdown(f"### 📸 Segae Identity Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    for i, slide in enumerate(slides):
        if slide['TYPE'] == 'COVER': img = bg_cover.copy()
        elif slide['TYPE'] == 'OUTRO': img = bg_outro.copy()
        else: img = bg_blur.copy()
            
        draw = ImageDraw.Draw(img, 'RGBA')
        
        # 폰트 생성 (매번 BytesIO 새로 생성 -> 에러 해결)
        ft_head = ImageFont.truetype(BytesIO(title_font_bytes), 95)
        ft_desc = ImageFont.truetype(BytesIO(body_font_bytes), 48)
        ft_small = ImageFont.truetype(BytesIO(body_font_bytes), 30)
        ft_serif = ImageFont.truetype(BytesIO(serif_font_bytes), 90)
        
        # [공통] CI 로고 삽입
        if slide['TYPE'] != 'OUTRO':
            if logo_img:
                img.paste(logo_img, (50, 50), logo_img)
            else:
                draw.text((50, 50), "세상을 보는 눈", font=ft_small, fill="#FFD700")
                draw.text((50, 90), "세계일보", font=ImageFont.truetype(BytesIO(title_font_bytes), 50), fill="white")
            
            draw.text((950, 60), f"{i+1} / {len(slides)}", font=ft_small, fill="white")

        # [1] COVER
        if slide['TYPE'] == 'COVER':
            head = slide.get("HEAD", "")
            desc = slide.get("DESC", "")
            
            d_lines = wrap_text(desc, ft_desc, 980, draw)
            desc_h = len(d_lines) * 60
            curr_y = 1080 - 100 - desc_h 
            
            for line in d_lines:
                draw_text_safe(draw, line, ft_desc, 50, curr_y, "#eeeeee")
                curr_y += 60
            
            curr_y -= (desc_h + 30)
            draw.rectangle([(50, curr_y), (150, curr_y+10)], fill=color_main)
            
            h_lines = wrap_text(head, ft_head, 980, draw)
            head_h = len(h_lines) * 110
            curr_y -= (head_h + 30)
            
            for line in h_lines:
                draw_text_safe(draw, line, ft_head, 50, curr_y, "white")
                curr_y += 110

        # [2] CONTENT (레이아웃 변주)
        elif slide['TYPE'] == 'CONTENT':
            layout = random.choice(['BOX', 'LEFT_BAR', 'QUOTE'])
            head = slide.get("HEAD", "")
            desc = slide.get("DESC", "")
            
            if layout == 'BOX':
                h_lines = wrap_text(head, ft_head, 850, draw)
                d_lines = wrap_text(desc, ft_desc, 850, draw)
                
                box_h = (len(h_lines)*110) + (len(d_lines)*65) + 120
                start_y = (1080 - box_h) / 2
                
                draw_rounded_box(draw, (80, start_y, 1000, start_y + box_h), 30, (0, 0, 0, 140))
                
                txt_y = start_y + 50
                for line in h_lines:
                    draw.text((120, txt_y), line, font=ft_head, fill=color_main)
                    txt_y += 110
                txt_y += 20
                for line in d_lines:
                    draw.text((120, txt_y), line, font=ft_desc, fill="white")
                    txt_y += 65
                    
            elif layout == 'LEFT_BAR':
                h_lines = wrap_text(head, ft_head, 900, draw)
                d_lines = wrap_text(desc, ft_desc, 900, draw)
                total_h = (len(h_lines)*110) + (len(d_lines)*65) + 60
                start_y = (1080 - total_h) / 2
                
                draw.rectangle([(60, start_y), (75, start_y + total_h)], fill=color_main)
                for line in h_lines:
                    draw_text_with_shadow(draw, (100, start_y), line, ft_head)
                    start_y += 110
                start_y += 30
                for line in d_lines:
                    draw_text_with_shadow(draw, (100, start_y), line, ft_desc, fill="#dddddd")
                    start_y += 65
                    
            elif layout == 'QUOTE':
                draw.text((80, 250), "“", font=ImageFont.truetype(BytesIO(serif_font_bytes), 400), fill=(255, 255, 255, 30))
                h_lines = wrap_text(head, ft_head, 850, draw)
                d_lines = wrap_text(desc, ft_desc, 850, draw)
                start_y = 450
                for line in h_lines:
                    draw_text_with_shadow(draw, (150, start_y), line, ft_head)
                    start_y += 110
                draw.line((150, start_y+20, 350, start_y+20), fill=color_main, width=6)
                start_y += 60
                for line in d_lines:
                    draw_text_with_shadow(draw, (150, start_y), line, ft_desc, fill="#cccccc")
                    start_y += 65

        # [3] OUTRO
        elif slide['TYPE'] == 'OUTRO':
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=ft_serif)
            w = bbox[2] - bbox[0]
            draw.text(((1080-w)/2, 350), slogan, font=ft_serif, fill="white")
            
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=ft_desc)
            w2 = bbox2[2] - bbox2[0]
            draw.text(((1080-w2)/2, 480), brand, font=ft_desc, fill="#dddddd")
            
            qr_img = generate_qr_code(url).resize((220, 220))
            qr_x = (1080 - 240) // 2
            qr_y = 650
            draw_rounded_box(draw, (qr_x, qr_y, qr_x+240, qr_y+240), 20, "white")
            img.paste(qr_img, (qr_x+10, qr_y+10))
            
            msg = "기사 원문 보러가기"
            bbox3 = draw.textbbox((0, 0), msg, font=ft_small)
            w3 = bbox3[2] - bbox3[0]
            draw.text(((1080-w3)/2, 910), msg, font=ft_small, fill="white")

        generated_images.append(img)
        with tabs[i]: st.image(img, caption=f"Page {i+1}")

    # --- 다운로드 ---
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for i, img in enumerate(generated_images):
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='PNG')
            zf.writestr(f"card_{i+1:02d}.png", img_byte_arr.getvalue())
    st.download_button("💾 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_news_v9.zip", "application/zip", use_container_width=True)
import streamlit as st
import google.generativeai as genai
from newspaper import Article, Config
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageStat
import fitz
from io import BytesIO
import re
import random
import zipfile
import qrcode
from datetime import datetime

# --- 페이지 설정 ---
st.set_page_config(page_title="One-Click News v8.0", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v8.1 Segae Identity)")
st.markdown("### 💎 세계일보 CI & 글씨체 적용")

# --- 폰트 및 로고 리소스 준비 ---
@st.cache_resource
def get_resources():
    resources = {}
    try:
        # 1. 폰트 (Google Fonts에서 유사 폰트 로드)
        # 제목용: Gmarket Sans (두껍고 힘있는 고딕)
        resources['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf", timeout=10).content
        # 본문용: Noto Sans KR (가독성)
        resources['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        # 명조: Noto Serif KR (감성)
        resources['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
        
        # 2. 로고 (임시: 온라인 로고 사용, 실제 운영시 로컬 파일 경로로 변경 가능)
        # 투명 배경의 세계일보 로고나 심볼이 필요합니다. 여기선 텍스트로 대체하는 로직을 기본으로 하되, 
        # 사용자가 로고를 업로드하면 그걸 쓰도록 구현했습니다.
    except: return None
    return resources

# --- 디자인 유틸리티 ---
def create_gradient_bottom(width, height):
    # 하단 30%부터 급격하게 어두워지는 그라데이션 (얼굴 사수용)
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    start_y = int(height * 0.6) # 60% 지점부터 시작
    for y in range(start_y, height):
        alpha = int(255 * ((y - start_y) / (height - start_y)) * 1.5) # 매우 진하게
        if alpha > 240: alpha = 240
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return overlay

def draw_text_safe(draw, text, font, x, y, color="white"):
    # 가독성을 위한 외곽선(Stroke) 효과
    stroke_width = 3
    stroke_color = "black"
    draw.text((x-stroke_width, y), text, font=font, fill=stroke_color)
    draw.text((x+stroke_width, y), text, font=font, fill=stroke_color)
    draw.text((x, y-stroke_width), text, font=font, fill=stroke_color)
    draw.text((x, y+stroke_width), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=color)

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

def hex_to_rgb(hex_color):
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join([c * 2 for c in hex_color])
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except: 
        return (255, 255, 255)

def relative_luminance(rgb):
    def channel(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

def contrast_ratio(c1, c2):
    l1 = relative_luminance(c1)
    l2 = relative_luminance(c2)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)

def pick_contrast_text_color(bg_rgb, preferred_hex, min_ratio=4.5):
    preferred_rgb = hex_to_rgb(preferred_hex)
    if contrast_ratio(bg_rgb, preferred_rgb) >= min_ratio:
        return preferred_hex
    # Fallback to white/black depending on higher contrast
    white = (255, 255, 255)
    black = (15, 15, 15)
    return "#FFFFFF" if contrast_ratio(bg_rgb, white) >= contrast_ratio(bg_rgb, black) else "#0F0F0F"

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
        title_preview_bytes = selected_title_font_file.getvalue() if selected_title_font_file else get_resources()['title']
        body_preview_bytes = selected_font_file.getvalue() if selected_font_file else get_resources()['body']
        serif_preview_bytes = selected_serif_font_file.getvalue() if selected_serif_font_file else get_resources()['serif']

        st.markdown("#### 폰트 미리보기")
        title_preview = render_font_preview(title_preview_bytes, "제목 미리보기: 세계일보 카드뉴스", size=34)
        body_preview = render_font_preview(body_preview_bytes, "본문 미리보기: 세상을 보는 눈, 세계일보", size=28)
        serif_preview = render_font_preview(serif_preview_bytes, "명조 미리보기: First in, Last out", size=30)

        if title_preview: st.image(title_preview, use_container_width=True)
        if body_preview: st.image(body_preview, use_container_width=True)
        if serif_preview: st.image(serif_preview, use_container_width=True)
    except:
        st.caption("폰트 미리보기를 표시할 수 없습니다.")

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
        
        # 2. 배경 처리 (Cover/Outro용 선명한 버전)
        bg_sharp = base_img.copy()
        grad_bottom = create_gradient_bottom(1080, 1080) # 하단 진한 그라데이션
        bg_sharp.paste(grad_bottom, (0,0), grad_bottom)
        
        # 3. 배경 처리 (Content용 블러 버전)
        bg_blur = base_img.copy()
        bg_blur = bg_blur.filter(ImageFilter.GaussianBlur(20)) # 강한 블러 (가독성 UP)
        bg_blur = ImageEnhance.Brightness(bg_blur).enhance(0.6) # 어둡게
        
        # 4. Outro 단색 배경
        try: bg_outro = Image.new('RGB', (1080, 1080), color=color_main)
        except: bg_outro = Image.new('RGB', (1080, 1080), color='#1a1a2e')

        # 5. 로고 준비
        logo_img = None
        if selected_logo_file:
            logo_name = selected_logo_file.name.lower()
            logo_bytes = selected_logo_file.getvalue()
            if logo_name.endswith(".ai"):
                logo_img = render_ai_to_image(logo_bytes)
            else:
                logo_img = Image.open(BytesIO(logo_bytes)).convert("RGBA")

            if logo_img:
                # 로고 리사이즈 (너비 250px 기준)
                aspect = logo_img.height / logo_img.width
                logo_img = logo_img.resize((250, int(250 * aspect)))
            else:
                st.warning("AI 로고 변환에 실패했습니다. PNG/JPG로 다시 업로드해 주세요.")
            
    except: st.error("이미지 처리 실패"); st.stop()

    # --- 렌더링 루프 ---
    res = get_resources()
    if not res: st.error("폰트 로딩 실패"); st.stop()
    
    st.markdown(f"### 📸 Segae Identity Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    for i, slide in enumerate(slides):
        # 배경 선택 로직
        if slide.get("TYPE") == "COVER":
            img = bg_sharp.copy() # 선명 + 하단 그라데이션
        elif slide.get("TYPE") == "OUTRO":
            img = bg_outro.copy() # 단색
        else:
            img = bg_blur.copy() # 흐림 + 어둡게
            
        draw = ImageDraw.Draw(img)
        
        # 폰트
        title_font_bytes = selected_title_font_file.getvalue() if selected_title_font_file else res['title']
        body_font_bytes = selected_font_file.getvalue() if selected_font_file else res['body']
        serif_font_bytes = selected_serif_font_file.getvalue() if selected_serif_font_file else res['serif']
        f_head = ImageFont.truetype(BytesIO(title_font_bytes), 95) # 더 키움
        f_desc = ImageFont.truetype(BytesIO(body_font_bytes), 48)
        f_serif = ImageFont.truetype(BytesIO(serif_font_bytes), 90)
        f_small = ImageFont.truetype(BytesIO(body_font_bytes), 30)
        
        # [공통] CI 로고 삽입 (좌측 상단)
        if slide.get("TYPE") != "OUTRO":
            if logo_img:
                img.paste(logo_img, (50, 50), logo_img) # 투명 배경 합성
            else:
                # 로고 없으면 텍스트로 대체 (고급스러운 명조)
                draw.text((50, 50), "세상을 보는 눈", font=f_small, fill="#FFD700")
                draw.text((50, 90), "세계일보", font=ImageFont.truetype(BytesIO(title_font_bytes), 50), fill="white")

            # 페이지 번호 (우측 상단)
            draw.text((950, 60), f"{i+1} / {len(slides)}", font=f_small, fill="white")

        # [SLIDE 1: COVER] - 하단 집중, 얼굴 사수
        if slide.get("TYPE") == "COVER":
            head = slide.get("HEAD", "")
            desc = slide.get("DESC", "")
            
            # 본문 (맨 바닥)
            d_lines = wrap_text(desc, f_desc, 980, draw)
            desc_h = len(d_lines) * 60
            current_y = 1080 - 100 - desc_h 
            
            for line in d_lines:
                draw_text_safe(draw, line, f_desc, 50, current_y, "#eeeeee")
                current_y += 60
            
            # 포인트 바 (제목 위)
            current_y -= (desc_h + 30)
            draw.rectangle([(50, current_y), (150, current_y+10)], fill=color_main)
            
            # 제목 (그 위)
            h_lines = wrap_text(head, f_head, 980, draw)
            head_h = len(h_lines) * 110
            current_y -= (head_h + 30)
            
            for line in h_lines:
                # 제목은 흰색 + 강한 그림자
                draw_text_safe(draw, line, f_head, 50, current_y, "white")
                current_y += 110

        # [SLIDE 2~7: CONTENT] - 블러 배경 위 텍스트
        elif slide.get("TYPE") == "CONTENT":
            head = slide.get("HEAD", "")
            desc = slide.get("DESC", "")
            
            # 제목 (중앙 상단 배치로 변경 - 블러 배경이라 얼굴 가려도 됨)
            # 아니면 통일성을 위해 하단 배치 유지하되, 블러 처리로 텍스트 가독성 최우선
            
            # 여기서는 '가독성'이 핵심이므로 중앙 정렬 박스 스타일 적용
            h_lines = wrap_text(head, f_head, 900, draw)
            d_lines = wrap_text(desc, f_desc, 900, draw)
            
            # 전체 텍스트 높이 계산
            total_h = (len(h_lines) * 110) + (len(d_lines) * 65) + 50
            start_y = (1080 - total_h) / 2
            
            # 배경 평균색을 기반으로 제목 대비 색상 선택
            title_box_top = max(0, int(start_y - 20))
            title_box_bottom = min(1080, int(start_y + (len(h_lines) * 110) + 20))
            title_box = (90, title_box_top, 990, title_box_bottom)
            try:
                avg_rgb = tuple(int(c) for c in ImageStat.Stat(img.crop(title_box)).mean[:3])
            except:
                avg_rgb = (30, 30, 30)
            title_color = pick_contrast_text_color(avg_rgb, color_main, min_ratio=4.5)
            
            # 제목 출력
            for line in h_lines:
                draw.text((90, start_y), line, font=f_head, fill=title_color) # 배경 대비 색상
                start_y += 110
            
            # 구분선
            draw.line((90, start_y, 290, start_y), fill="white", width=5)
            start_y += 50
            
            # 본문 출력
            for line in d_lines:
                draw.text((90, start_y), line, font=f_desc, fill="white")
                start_y += 65

        # [SLIDE 8: OUTRO]
        elif slide.get("TYPE") == "OUTRO":
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=f_serif)
            w = bbox[2] - bbox[0]
            draw.text(((1080-w)/2, 350), slogan, font=f_serif, fill="white")
            
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=f_desc)
            w2 = bbox2[2] - bbox2[0]
            draw.text(((1080-w2)/2, 480), brand, font=f_desc, fill="#dddddd")
            
            # QR 코드
            qr_img = generate_qr_code(url).resize((220, 220))
            qr_bg_x = (1080 - 240) // 2
            qr_bg_y = 650
            draw.rectangle([(qr_bg_x, qr_bg_y), (qr_bg_x + 240, qr_bg_y + 240)], fill="white")
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
    st.download_button("💾 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_identity.zip", "application/zip", use_container_width=True)
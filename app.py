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
st.set_page_config(page_title="One-Click News v7.0", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v7.0 Bio Edition)")
st.markdown("### 💎 인물 얼굴 '절대 사수' & 서사적 깊이 강화 (6~8장 강제)")

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

# --- 디자인 유틸리티 (얼굴 사수용 그라데이션) ---
def create_bottom_gradient(width, height):
    # 하단 40%부터 어두워지기 시작해서 맨 아래는 완전 블랙
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    start_y = int(height * 0.5) # 중간부터 시작
    for y in range(start_y, height):
        # 알파값: 0 -> 240 (점진적)
        alpha = int(240 * ((y - start_y) / (height - start_y)))
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return overlay

def draw_text_safe(draw, text, font, x, y, color="white"):
    # 그림자 강하게 (가독성 확보)
    draw.text((x+2, y+2), text, font=font, fill="black")
    draw.text((x+2, y-2), text, font=font, fill="black")
    draw.text((x-2, y+2), text, font=font, fill="black")
    draw.text((x-2, y-2), text, font=font, fill="black")
    # 본문
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

def generate_qr_code(link):
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(link)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")

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

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")
    user_image = st.file_uploader("직접 업로드 (1순위)", type=['png', 'jpg', 'jpeg'])

# --- 메인 ---
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

if st.button("🚀 얼굴 안 가리는 카드뉴스 제작"):
    if not api_key or not url: st.error("설정 확인 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사 심층 분석 중...")
    
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- [AI 프롬프트: 서사 구조 및 분량 강제] ---
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # 기사 길이에 따른 최소 장수 계산
        min_slides = 6 if len(text) > 1000 else 5
        
        prompt = f"""
        당신은 세계일보의 '심층 기획 에디터'입니다.
        
        [기사 정보]
        제목: {title}
        내용: {text[:5000]}
        
        [절대 규칙]
        1. **분량:** 무조건 **{min_slides}장 이상 8장 이하**로 구성할 것. (내용을 깊이 있게 다룰 것)
        2. **구조 (인물/사건 중심):**
           - SLIDE 1 (COVER): 제목 + 요약
           - SLIDE 2~{min_slides-1} (STORY): 시간 순서(Chronological) 또는 핵심 사건별로 전개.
             * 중요: 각 장마다 '구체적인 사실(Fact)'과 '맥락(Context)'을 풍부하게 담을 것. 
             * 단순 나열 금지. "A했다."가 아니라 "A함으로써 B라는 결과를 낳았다" 식으로 서술.
           - SLIDE {min_slides} (EVAL): 공과 과, 또는 의의와 전망.
        3. **텍스트:** - HEAD: 15자 이내 (핵심)
           - DESC: 80자 내외 (2~3문장, 구체적 서술)
        4. **컬러:** 기사 분위기에 맞는 짙은 단색(Hex) 하나 추출.
        
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
        
        # [얼굴 사수] 전체적으로 살짝만 어둡게 하고, 하단 그라데이션을 따로 합성
        enhancer = ImageEnhance.Brightness(base_img)
        base_img_dim = enhancer.enhance(0.9) # 원본 거의 유지
        
        gradient = create_bottom_gradient(1080, 1080)
        bg_content = Image.alpha_composite(base_img_dim.convert('RGBA'), gradient)
        
        try: bg_outro = Image.new('RGB', (1080, 1080), color=color_main)
        except: bg_outro = Image.new('RGB', (1080, 1080), color='#1a1a2e')
            
    except: st.error("이미지 실패"); st.stop()

    # --- 렌더링 루프 ---
    fonts = get_fonts()
    if not fonts: st.error("폰트 로딩 실패"); st.stop()
    
    st.markdown(f"### 📸 Bio Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    for i, slide in enumerate(slides):
        if slide.get("TYPE") == "OUTRO": img = bg_outro.copy()
        else: img = bg_content.copy() # 하단 그라데이션 적용된 배경
        
        draw = ImageDraw.Draw(img)
        
        # 폰트
        f_head = ImageFont.truetype(BytesIO(fonts['title']), 80)
        f_desc = ImageFont.truetype(BytesIO(fonts['body']), 45)
        f_small = ImageFont.truetype(BytesIO(fonts['body']), 30)
        f_serif = ImageFont.truetype(BytesIO(fonts['serif']), 90)
        
        # [상단 정보] - 얼굴 피해서 아주 작게
        if slide.get("TYPE") != "OUTRO":
            draw.text((50, 50), "SEGYE BRIEFING", font=f_small, fill="#FFD700")
            draw.text((950, 50), f"{i+1} / {len(slides)}", font=f_small, fill="white")

        # [디자인 로직: 무조건 하단 배치 (Bottom Alignment)]
        if slide.get("TYPE") == "COVER" or slide.get("TYPE") == "CONTENT":
            head = slide.get("HEAD", "")
            desc = slide.get("DESC", "")
            
            # 본문 먼저 계산 (맨 아래부터 위로 쌓기)
            d_lines = wrap_text(desc, f_desc, 980, draw)
            desc_h = len(d_lines) * 60
            
            # 헤드라인 계산
            h_lines = wrap_text(head, f_head, 980, draw)
            head_h = len(h_lines) * 100
            
            # 기준점: 바닥에서 100px 띄움
            current_y = 1080 - 100 - desc_h 
            
            # 설명 쓰기
            for line in d_lines:
                draw_text_safe(draw, line, f_desc, 50, current_y, "#dddddd")
                current_y += 60
            
            # 장식용 바 (Bar)
            current_y -= (desc_h + 40) # 설명 위로 이동
            draw.rectangle([(50, current_y), (150, current_y+10)], fill=color_main)
            
            # 헤드라인 쓰기 (바 위로 이동)
            current_y -= (head_h + 30)
            for line in h_lines:
                draw_text_safe(draw, line, f_head, 50, current_y, "white")
                current_y += 100

        # [OUTRO] - 기존 유지
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
    st.download_button("💾 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_bio_edition.zip", "application/zip", use_container_width=True)
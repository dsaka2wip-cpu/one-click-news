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

# --- 페이지 설정 ---
st.set_page_config(page_title="One-Click News v4.0", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v4.0 Magazine Edition)")
st.markdown("### 💎 품격 있는 '매거진 스타일' 디자인 시스템 적용")

# --- 폰트 준비 (고딕 & 명조 믹스매치) ---
@st.cache_resource
def get_fonts():
    fonts = {}
    try:
        # 제목용 (강렬함): Black Han Sans
        fonts['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf", timeout=10).content
        # 본문용 (가독성): Nanum Gothic Bold
        fonts['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        # 엔딩/인용구용 (감성/명조): Nanum Myeongjo ExtraBold
        fonts['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return fonts

# --- 디자인 유틸리티 함수 (핵심 업그레이드) ---

# 1. 시네마틱 그라데이션 생성
def create_gradient_overlay(width, height, top_opacity=20, bottom_opacity=230):
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        # 선형 보간 (Linear Interpolation)
        alpha = int(top_opacity + (bottom_opacity - top_opacity) * (y / height))
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return overlay

# 2. 텍스트 그림자 효과 (가독성 끝판왕)
def draw_text_with_shadow(draw, position, text, font, text_color="white", shadow_color="black", shadow_offset=(3, 3)):
    x, y = position
    # 그림자 먼저 그리기
    draw.text((x + shadow_offset[0], y + shadow_offset[1]), text, font=font, fill=shadow_color)
    # 본문 그리기
    draw.text((x, y), text, font=font, fill=text_color)

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

# --- 기본 유틸리티 ---
def get_fallback_image(keyword):
    # (백업용 이미지 로직 유지)
    return "https://images.unsplash.com/photo-1550684848-fac1c5b4e853?q=80&w=1000"

def clean_text_strict(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'[#\*]', '', text)
    return text.strip()

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

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.markdown("---")
    user_image = st.file_uploader("직접 업로드 (1순위)", type=['png', 'jpg', 'jpeg'])

# --- 메인 ---
url = st.text_input("기사 URL 입력", placeholder="https://www.segye.com/...")

if st.button("🚀 매거진 스타일 제작"):
    if not api_key or not url: st.error("설정 확인 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사를 분석 중입니다...")
    
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- [AI 프롬프트: 매거진 스타일 기획] ---
    try:
        status.info("🧠 AI가 매거진 스타일로 기획 중입니다...")
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""
        당신은 세계일보의 '수석 아트 디렉터'입니다.
        고급 매거진(TIME, Vogue) 스타일의 카드뉴스를 기획하세요.
        
        [기사 정보]
        제목: {title}
        내용: {text[:4000]}
        
        [필수 규칙]
        1. **분량:** 기사 깊이에 따라 **4~8장** 자동 결정.
        2. **카피라이팅:** - 제목은 2줄 이내로 강렬하게.
           - 본문은 **'대화하듯'** 자연스럽게 (최대 60자).
           - 딱딱한 개조식(~함, ~음) 절대 금지.
        3. **디자인 키워드:** 기사 분위기에 맞는 **포인트 컬러(Hex)** 하나만 추출. (무조건 쨍하고 밝은 색으로. 예: #FFD700, #00FFFF, #FF007F)
        
        [출력 양식]
        COLOR_MAIN: #Hex
        
        [SLIDE 1]
        TYPE: COVER
        TEXT: [헤드라인]
        SUB: [서브 카피]
        
        [SLIDE 2]
        TYPE: CONTENT
        TEXT: [본문 내용]
        
        ...
        
        [SLIDE N]
        TYPE: OUTRO
        TEXT: First in, Last out
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
                current_slide = {"TEXT": "", "SUB": "", "TYPE": ""}
            elif line.startswith("TYPE:"): current_slide["TYPE"] = line.split(":")[1].strip()
            elif line.startswith("TEXT:"): current_slide["TEXT"] = line.split("TEXT:")[1].strip()
            elif line.startswith("SUB:"): current_slide["SUB"] = line.split("SUB:")[1].strip()
            
        if current_slide: slides.append(current_slide)
        status.success(f"✅ 기획 완료: 총 {len(slides)}장")
        
    except Exception as e:
        st.error(f"기획 오류: {e}")
        st.stop()

    # --- 이미지 및 디자인 소스 준비 ---
    try:
        # 1. 베이스 이미지 로드
        if user_image: base_img = Image.open(user_image)
        elif img_url:
            headers = {'User-Agent': 'Mozilla/5.0'}
            base_img = Image.open(BytesIO(requests.get(img_url, headers=headers, timeout=5).content))
        else:
            base_img = Image.new('RGB', (1080, 1080), color='#1a1a2e')
            
        base_img = base_img.convert('RGB').resize((1080, 1080))
        
        # 2. 이미지 톤 보정 (약간 어둡고 차분하게 -> 글자 강조)
        enhancer = ImageEnhance.Brightness(base_img)
        base_img = enhancer.enhance(0.8) # 밝기 80%로 낮춤
        
        # 3. 그라데이션 오버레이 생성 (상단 투명 -> 하단 블랙)
        gradient = create_gradient_overlay(1080, 1080, top_opacity=30, bottom_opacity=240)
        
        # 4. 최종 배경 합성
        bg_final = Image.alpha_composite(base_img.convert('RGBA'), gradient)
        
    except:
        base_img = Image.new('RGB', (1080, 1080), color='#000000')
        bg_final = base_img

    # --- 렌더링 루프 ---
    fonts = get_fonts()
    if not fonts: st.error("폰트 로딩 실패"); st.stop()
    
    st.markdown(f"### 📸 Magazine Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    for i, slide in enumerate(slides):
        img = bg_final.copy()
        draw = ImageDraw.Draw(img)
        
        # 폰트 설정 (계층 구조 명확화)
        font_headline = ImageFont.truetype(BytesIO(fonts['title']), 100) # 더 키움
        font_sub = ImageFont.truetype(BytesIO(fonts['body']), 45)
        font_body = ImageFont.truetype(BytesIO(fonts['body']), 60)
        font_serif_big = ImageFont.truetype(BytesIO(fonts['serif']), 90) # 명조체
        font_tag = ImageFont.truetype(BytesIO(fonts['body']), 35)
        
        # [SLIDE 1: COVER] - 압도적인 타이포그래피
        if slide.get("TYPE") == "COVER":
            # 1. 브랜드 태그 (좌측 상단, 박스형)
            draw.rectangle([(50, 60), (350, 120)], fill=color_main)
            draw.text((70, 72), "SEGYE BRIEFING", font=font_tag, fill="black")
            
            # 2. 메인 헤드라인 (좌측 하단 배치)
            title_text = slide.get("TEXT", "")
            lines = wrap_text(title_text, font_headline, 980, draw)
            
            # 위치 계산 (하단에서 위로 쌓기)
            start_y = 850 - (len(lines) * 110)
            for line in lines:
                draw_text_with_shadow(draw, (60, start_y), line, font_headline, shadow_color="#000000")
                start_y += 110
            
            # 3. 부제 (헤드라인 아래)
            if slide.get("SUB"):
                draw_text_with_shadow(draw, (60, start_y + 20), slide["SUB"], font_sub, text_color="#dddddd")

        # [SLIDE 2~N: CONTENT] - 여백과 가독성
        elif slide.get("TYPE") == "CONTENT":
            # 1. 페이지 번호 (우측 상단)
            draw_text_with_shadow(draw, (950, 60), f"{i+1}", font_sub)
            
            # 2. 디자인 바 (좌측, 포인트 컬러)
            draw.rectangle([(60, 250), (75, 400)], fill=color_main)
            
            # 3. 본문 텍스트 (좌측 정렬, 시각적 안정감)
            body_text = clean_text_strict(slide.get("TEXT", ""))
            lines = wrap_text(body_text, font_body, 900, draw)
            
            start_y = 250
            for line in lines:
                draw_text_with_shadow(draw, (100, start_y), line, font_body)
                start_y += 85
            
            # 4. 큰 따옴표 장식 (배경에 은은하게 깔기)
            # 명조체 큰 따옴표를 투명도 줘서 그림

        # [SLIDE LAST: OUTRO] - 여운이 남는 명조체 엔딩
        elif slide.get("TYPE") == "OUTRO":
            # 중앙 정렬 계산
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=font_serif_big)
            w = bbox[2] - bbox[0]
            
            # 1. 슬로건 (명조체, 가운데)
            draw_text_with_shadow(draw, ((1080-w)/2, 450), slogan, font=font_serif_big, text_color=color_main)
            
            # 2. 로고
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=font_sub)
            w2 = bbox2[2] - bbox2[0]
            draw_text_with_shadow(draw, ((1080-w2)/2, 600), brand, font=font_sub)
            
            # 3. 얇은 라인 장식
            draw.line((400, 420, 680, 420), fill="white", width=2)
            draw.line((400, 680, 680, 680), fill="white", width=2)

        generated_images.append(img)
        with tabs[i]:
            st.image(img, caption=f"Page {i+1}")

    # --- 다운로드 ---
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for i, img in enumerate(generated_images):
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='PNG')
            zf.writestr(f"card_{i+1:02d}.png", img_byte_arr.getvalue())
            
    st.download_button("💾 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_magazine.zip", "application/zip", use_container_width=True)
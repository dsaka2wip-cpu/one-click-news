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
st.set_page_config(page_title="One-Click News v7.5", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v7.5 Hook Master)")
st.markdown("### ⚡ 0.3초 훅(Hook) & 후반부 심층 콘텐츠(Deep Dive) 강화")

# --- 폰트 준비 ---
@st.cache_resource
def get_fonts():
    fonts = {}
    try:
        # 제목 (아주 두꺼운 고딕): Black Han Sans
        fonts['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf", timeout=10).content
        # 본문 (가독성): Nanum Gothic Bold
        fonts['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        # 명조 (인용구/엔딩): Nanum Myeongjo ExtraBold
        fonts['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return fonts

# --- 디자인 유틸리티 ---
def create_bottom_gradient(width, height):
    # 하단 50%부터 진하게 올라오는 그라데이션 (얼굴 사수용)
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    start_y = int(height * 0.4) 
    for y in range(start_y, height):
        alpha = int(255 * ((y - start_y) / (height - start_y)) * 1.2) # 더 진하게 (1.2배)
        if alpha > 255: alpha = 255
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return overlay

def draw_text_safe(draw, text, font, x, y, color="white"):
    # 강력한 그림자 (가독성 최우선)
    shadow_color = "black"
    offset = 3
    draw.text((x+offset, y+offset), text, font=font, fill=shadow_color)
    draw.text((x-offset, y+offset), text, font=font, fill=shadow_color)
    draw.text((x+offset, y-offset), text, font=font, fill=shadow_color)
    draw.text((x-offset, y-offset), text, font=font, fill=shadow_color)
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

if st.button("🚀 강렬한 훅(Hook) 만들기"):
    if not api_key or not url: st.error("설정 확인 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사를 입체적으로 분석 중입니다...")
    
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- [AI 프롬프트: 훅 강화 & 후반부 콘텐츠 강제] ---
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""
        당신은 세계일보의 '소셜 미디어 총괄 에디터'입니다.
        독자의 스크롤을 멈추게 하는 '강렬한 훅'과 '깊이 있는 분석'을 제공하세요.
        
        [기사 정보]
        제목: {title}
        내용: {text[:6000]}
        
        [절대 규칙 (엄수)]
        1. **총 8장 구성 (고정):** 내용이 짧아도 분석을 덧붙여서 무조건 8장을 채울 것.
        2. **슬라이드별 역할 (Role):**
           - **SLIDE 1 (HOOK):** 제목은 8자 이내로 아주 짧고 강렬하게 (예: "킹메이커의 퇴장"). 
             *부제는 독자의 호기심을 자극하는 질문이나 반전 문구 사용.*
           - **SLIDE 2~5 (STORY):** 기승전결에 따른 핵심 사건 전개. (구체적 팩트 포함)
           - **SLIDE 6 (QUOTES/KEYWORD):** 인물의 결정적 발언(명언)이나 핵심 키워드 3가지를 정리. (앞 내용 반복 금지)
           - **SLIDE 7 (IMPACT):** 이 사건이 한국 사회/정치에 미칠 영향이나 향후 전망. (기사에 없으면 통찰력을 발휘해 작성)
           - **SLIDE 8 (OUTRO):** First in, Last out
        3. **텍스트 길이:**
           - HEAD: 15자 이내 (1장은 8자 이내)
           - DESC: 80~100자 (충실하게 꽉 채울 것)
        4. **컬러:** 기사 분위기에 맞는 짙은 형광/원색 계열 코드 1개.
        
        [출력 양식]
        COLOR_MAIN: #Hex
        
        [SLIDE 1]
        TYPE: COVER
        TAG: [짧은태그] (예: ISSUE, 속보, 인물)
        HEAD: [초강력 제목]
        DESC: [호기심 자극 부제]
        
        [SLIDE 2]
        TYPE: CONTENT
        HEAD: ...
        DESC: ...
        
        ...
        
        [SLIDE 6]
        TYPE: CONTENT
        HEAD: [결정적 순간들]
        DESC: [인용구 또는 키워드 나열]
        
        [SLIDE 7]
        TYPE: CONTENT
        HEAD: [남겨진 과제와 전망]
        DESC: [심층 분석 내용]
        
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
                current_slide = {"HEAD": "", "DESC": "", "TYPE": "", "TAG": ""}
            elif line.startswith("TYPE:"): current_slide["TYPE"] = line.split(":")[1].strip()
            elif line.startswith("TAG:"): current_slide["TAG"] = line.split("TAG:")[1].strip()
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
        
        # [HOOK 강화] 배경을 더 어둡게 눌러서 텍스트 팝업 유도
        enhancer = ImageEnhance.Brightness(base_img)
        base_img_dim = enhancer.enhance(0.85) 
        
        gradient = create_bottom_gradient(1080, 1080)
        bg_content = Image.alpha_composite(base_img_dim.convert('RGBA'), gradient)
        
        try: bg_outro = Image.new('RGB', (1080, 1080), color=color_main)
        except: bg_outro = Image.new('RGB', (1080, 1080), color='#1a1a2e')
            
    except: st.error("이미지 실패"); st.stop()

    # --- 렌더링 루프 ---
    fonts = get_fonts()
    if not fonts: st.error("폰트 로딩 실패"); st.stop()
    
    st.markdown(f"### 📸 Hook Master Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    for i, slide in enumerate(slides):
        if slide.get("TYPE") == "OUTRO": img = bg_outro.copy()
        else: img = bg_content.copy() 
        
        draw = ImageDraw.Draw(img)
        
        # 폰트 사이즈 대폭 확대 (HOOK)
        f_head_cover = ImageFont.truetype(BytesIO(fonts['title']), 130) # 표지용 초대형 폰트
        f_head = ImageFont.truetype(BytesIO(fonts['title']), 85)
        f_desc = ImageFont.truetype(BytesIO(fonts['body']), 48)
        f_tag = ImageFont.truetype(BytesIO(fonts['body']), 35)
        f_serif = ImageFont.truetype(BytesIO(fonts['serif']), 90)
        
        # [상단 정보]
        if slide.get("TYPE") != "OUTRO":
            # 페이지 표시줄 (상단 전체 가로지르는 바)
            draw.rectangle([(0, 0), (1080, 15)], fill="#333333")
            prog = 1080 * ((i+1)/len(slides))
            draw.rectangle([(0, 0), (prog, 15)], fill=color_main)

        # [SLIDE 1: COVER] - 강렬한 훅
        if slide.get("TYPE") == "COVER":
            # 1. 상단 태그 (Badge)
            tag_text = slide.get("TAG", "ISSUE")
            draw.rectangle([(50, 80), (250, 150)], fill=color_main)
            draw.text((80, 95), tag_text, font=f_tag, fill="black")
            
            # 2. 메인 헤드라인 (초대형)
            head = slide.get("HEAD", "")
            h_lines = wrap_text(head, f_head_cover, 980, draw)
            
            # 위치: 화면 중앙보다 약간 위
            start_y = 400
            for line in h_lines:
                # 글자 색상: 흰색 + 강한 그림자
                draw_text_safe(draw, line, f_head_cover, 50, start_y, "white")
                start_y += 150
            
            # 3. 부제 (설명)
            desc = slide.get("DESC", "")
            d_lines = wrap_text(desc, f_desc, 980, draw)
            dy = start_y + 30
            
            # 노란색 강조선
            draw.line((50, dy, 200, dy), fill=color_main, width=10)
            dy += 40
            
            for line in d_lines:
                draw_text_safe(draw, line, f_desc, 50, dy, "#eeeeee")
                dy += 60

        # [SLIDE 2~N: CONTENT] - 하단 집중형
        elif slide.get("TYPE") == "CONTENT":
            head = slide.get("HEAD", "")
            desc = slide.get("DESC", "")
            
            # 본문 (맨 아래)
            d_lines = wrap_text(desc, f_desc, 980, draw)
            desc_h = len(d_lines) * 60
            current_y = 1080 - 100 - desc_h 
            
            for line in d_lines:
                draw_text_safe(draw, line, f_desc, 50, current_y, "#dddddd")
                current_y += 60
            
            # 제목 (그 위)
            h_lines = wrap_text(head, f_head, 980, draw)
            head_h = len(h_lines) * 100
            current_y -= (desc_h + head_h + 60)
            
            # 포인트 바
            draw.rectangle([(50, current_y), (150, current_y+10)], fill=color_main)
            current_y += 30
            
            for line in h_lines:
                draw_text_safe(draw, line, f_head, 50, current_y, "white")
                current_y += 100

        # [OUTRO]
        elif slide.get("TYPE") == "OUTRO":
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=f_serif)
            w = bbox[2] - bbox[0]
            draw.text(((1080-w)/2, 350), slogan, font=f_serif, fill="white")
            
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=f_desc)
            w2 = bbox2[2] - bbox2[0]
            draw.text(((1080-w2)/2, 480), brand, font=f_desc, fill="#dddddd")
            
            # QR
            qr_img = generate_qr_code(url).resize((220, 220))
            qr_bg_x = (1080 - 240) // 2
            qr_bg_y = 650
            draw.rectangle([(qr_bg_x, qr_bg_y), (qr_bg_x + 240, qr_bg_y + 240)], fill="white")
            img.paste(qr_img, (qr_bg_x + 10, qr_bg_y + 10))
            
            msg = "기사 원문 보러가기"
            bbox3 = draw.textbbox((0, 0), msg, font=f_tag)
            w3 = bbox3[2] - bbox3[0]
            draw.text(((1080-w3)/2, 910), msg, font=f_tag, fill="white")

        generated_images.append(img)
        with tabs[i]: st.image(img, caption=f"Page {i+1}")

    # --- 다운로드 ---
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for i, img in enumerate(generated_images):
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='PNG')
            zf.writestr(f"card_{i+1:02d}.png", img_byte_arr.getvalue())
    st.download_button("💾 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_hook_master.zip", "application/zip", use_container_width=True)
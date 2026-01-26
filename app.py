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
st.set_page_config(page_title="One-Click News v4.1", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v4.1 Kind Magazine)")
st.markdown("### 💎 [제목+설명] 2단 구조로 '친절하고 깊이 있는' 뉴스 생산")

# --- 폰트 준비 ---
@st.cache_resource
def get_fonts():
    fonts = {}
    try:
        # 제목용 (강렬함): Black Han Sans
        fonts['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf", timeout=10).content
        # 본문용 (가독성): Nanum Gothic Bold
        fonts['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        # 엔딩/명조 (감성): Nanum Myeongjo ExtraBold
        fonts['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return fonts

# --- 디자인 유틸리티 ---
def create_gradient_overlay(width, height, top_opacity=40, bottom_opacity=240):
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        alpha = int(top_opacity + (bottom_opacity - top_opacity) * (y / height))
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return overlay

def draw_text_with_shadow(draw, position, text, font, text_color="white", shadow_color="black", shadow_offset=(2, 2)):
    x, y = position
    draw.text((x + shadow_offset[0], y + shadow_offset[1]), text, font=font, fill=shadow_color)
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

if st.button("🚀 친절한 뉴스 만들기"):
    if not api_key or not url: st.error("설정 확인 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사를 정밀 분석 중입니다...")
    
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- [AI 프롬프트 수정: 제목과 설명 분리] ---
    try:
        status.info("🧠 AI가 제목과 본문을 나누어 '친절하게' 재구성 중입니다...")
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""
        당신은 세계일보의 '친절한 뉴스 에디터'입니다.
        독자가 이미지만 보고도 내용을 완벽히 이해하도록 [키워드]와 [설명]을 분리해서 작성하세요.
        
        [기사 정보]
        제목: {title}
        내용: {text[:4000]}
        
        [필수 규칙]
        1. **분량:** 기사 깊이에 따라 **5~8장** 사이.
        2. **구조 (엄수):**
           - **HEAD:** 핵심 키워드나 짧은 제목 (15자 이내, 임팩트)
           - **DESC:** 그 헤드라인이 무슨 뜻인지, 왜 중요한지 설명하는 문장 (2~3문장, 60~80자, 친절한 어투)
        3. **디자인 키워드:** 기사 분위기에 맞는 **포인트 컬러(Hex)** 추출. (밝은 톤 권장)
        
        [출력 양식]
        COLOR_MAIN: #Hex
        
        [SLIDE 1]
        TYPE: COVER
        HEAD: [메인 제목]
        DESC: [부제/요약]
        
        [SLIDE 2]
        TYPE: CONTENT
        HEAD: [핵심 키워드 1]
        DESC: [상세 설명 1 (친절하게)]
        
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
        status.success(f"✅ 기획 완료: 총 {len(slides)}장")
        
    except Exception as e:
        st.error(f"기획 오류: {e}")
        st.stop()

    # --- 이미지 준비 ---
    try:
        if user_image: base_img = Image.open(user_image)
        elif img_url:
            headers = {'User-Agent': 'Mozilla/5.0'}
            base_img = Image.open(BytesIO(requests.get(img_url, headers=headers, timeout=5).content))
        else:
            base_img = Image.new('RGB', (1080, 1080), color='#1a1a2e')
            
        base_img = base_img.convert('RGB').resize((1080, 1080))
        enhancer = ImageEnhance.Brightness(base_img)
        base_img = enhancer.enhance(0.7) # 조금 더 어둡게 (글자 잘 보이게)
        
        gradient = create_gradient_overlay(1080, 1080, top_opacity=50, bottom_opacity=230)
        bg_final = Image.alpha_composite(base_img.convert('RGBA'), gradient)
        
    except:
        base_img = Image.new('RGB', (1080, 1080), color='#000000')
        bg_final = base_img

    # --- 렌더링 루프 (2단 레이아웃 적용) ---
    fonts = get_fonts()
    if not fonts: st.error("폰트 로딩 실패"); st.stop()
    
    st.markdown(f"### 📸 Magazine Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    for i, slide in enumerate(slides):
        img = bg_final.copy()
        draw = ImageDraw.Draw(img)
        
        # 폰트
        font_head = ImageFont.truetype(BytesIO(fonts['title']), 85) # 헤드라인
        font_desc = ImageFont.truetype(BytesIO(fonts['body']), 48)  # 본문
        font_serif = ImageFont.truetype(BytesIO(fonts['serif']), 90) # 엔딩용
        font_small = ImageFont.truetype(BytesIO(fonts['body']), 30) # 페이지 번호
        
        # 페이지 번호
        draw_text_with_shadow(draw, (950, 60), f"{i+1}", font_small)

        # [SLIDE 1: COVER]
        if slide.get("TYPE") == "COVER":
            # 브랜드
            draw.rectangle([(50, 60), (350, 120)], fill=color_main)
            draw.text((70, 72), "SEGYE BRIEFING", font=font_small, fill="black")
            
            # 헤드라인 (중앙 하단)
            head_text = slide.get("HEAD", "")
            lines = wrap_text(head_text, font_head, 960, draw)
            start_y = 600 - (len(lines) * 50)
            for line in lines:
                draw_text_with_shadow(draw, (60, start_y), line, font_head, shadow_color="black")
                start_y += 100
            
            # 설명 (헤드라인 아래)
            if slide.get("DESC"):
                desc_text = slide.get("DESC", "")
                d_lines = wrap_text(desc_text, font_desc, 960, draw)
                dy = start_y + 40
                draw.line((60, dy, 260, dy), fill=color_main, width=8) # 구분선
                dy += 50
                for line in d_lines:
                    draw_text_with_shadow(draw, (60, dy), line, font_desc, text_color="#eeeeee")
                    dy += 60

        # [SLIDE 2~N: CONTENT] (2단 구조: 제목 + 설명)
        elif slide.get("TYPE") == "CONTENT":
            # 1. 헤드라인 (포인트 컬러) - 상단 배치
            head_text = slide.get("HEAD", "")
            lines = wrap_text(head_text, font_head, 900, draw)
            start_y = 350
            
            # 좌측 세로 바
            draw.rectangle([(60, start_y), (75, start_y + (len(lines)*100) + 20)], fill=color_main)
            
            for line in lines:
                draw_text_with_shadow(draw, (90, start_y), line, font_head) # 흰색
                start_y += 100
            
            # 2. 설명 (본문) - 헤드라인 아래
            desc_text = clean_text_strict(slide.get("DESC", ""))
            d_lines = wrap_text(desc_text, font_desc, 900, draw)
            
            dy = start_y + 40
            for line in d_lines:
                draw_text_with_shadow(draw, (90, dy), line, font_desc, text_color="#dddddd")
                dy += 65

        # [SLIDE LAST: OUTRO]
        elif slide.get("TYPE") == "OUTRO":
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=font_serif)
            w = bbox[2] - bbox[0]
            draw_text_with_shadow(draw, ((1080-w)/2, 450), slogan, font_serif, text_color=color_main)
            
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=font_desc)
            w2 = bbox2[2] - bbox2[0]
            draw_text_with_shadow(draw, ((1080-w2)/2, 600), brand, font_desc)
            
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
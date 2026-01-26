import streamlit as st
import google.generativeai as genai
from newspaper import Article, Config
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import re
import random

# --- 페이지 설정 ---
st.set_page_config(page_title="One-Click News v3.4", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v3.4 Tab View)")
st.markdown("### 🌊 4~8장 자동 생성 + 탭(Tab) 뷰어 (안정성 강화)")

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

# --- 이미지 라이브러리 (백업용) ---
def get_fallback_image(keyword):
    keyword = keyword.lower().strip()
    library = {
        "politics": ["https://images.unsplash.com/photo-1555848962-6e79363ec58f?q=80&w=1000"],
        "news": ["https://images.unsplash.com/photo-1550684848-fac1c5b4e853?q=80&w=1000"]
    }
    abstract_backgrounds = ["https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?q=80&w=1000"]
    for key, urls in library.items():
        if key in keyword: return random.choice(urls)
    return random.choice(abstract_backgrounds)

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

if st.button("🚀 카드뉴스 제작 시작"):
    if not api_key or not url: st.error("설정 확인 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사를 분석 중입니다...")
    
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- [AI 프롬프트: 4~8장 규칙] ---
    try:
        status.info("🧠 AI가 기사 호흡을 4~8장으로 최적화합니다...")
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""
        당신은 세계일보의 '비주얼 뉴스 에디터'입니다.
        독자가 '읽지 않고 보는' 직관적인 카드뉴스를 기획하세요.
        
        [기사 정보]
        제목: {title}
        내용: {text[:4000]}
        
        [필수 규칙]
        1. **분량 결정:** 기사의 깊이와 중요도에 따라 **4~8장** 사이로 자동 결정하세요.
           - 단순/속보 기사: 4장 (Hook -> 본문1,2 -> Outro)
           - 일반/해설 기사: 5~6장
           - 심층/기획 기사: 7~8장
        2. **텍스트 제한:** 각 슬라이드 본문은 **최대 2문장, 60자 이내**로 짧게 압축하세요. (가독성 최우선)
        3. **구성:** 기승전결(Hook -> Context -> Detail -> Conclusion -> Outro) 흐름을 유지하세요.
        
        [출력 양식]
        COLOR_MAIN: #Hex
        
        [SLIDE 1]
        TYPE: COVER
        TEXT: [강렬한 제목]
        SUB: [짧은 부제]
        
        [SLIDE 2]
        TYPE: CONTENT
        TEXT: [내용 1]
        
        ... (판단한 장수만큼 반복) ...
        
        [SLIDE N]
        TYPE: OUTRO
        TEXT: First in, Last out
        LOGO: 세상을 보는 눈, 세계일보
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
        
        status.success(f"✅ 기획 완료: 총 {len(slides)}장으로 구성됩니다.")
        
    except Exception as e:
        st.error(f"기획 오류: {e}")
        st.stop()

    # --- 이미지 준비 ---
    try:
        base_img = None
        if user_image: 
            base_img = Image.open(user_image)
        elif img_url:
            headers = {'User-Agent': 'Mozilla/5.0'}
            base_img = Image.open(BytesIO(requests.get(img_url, headers=headers, timeout=5).content))
        else:
            fallback_url = get_fallback_image("news")
            base_img = Image.open(BytesIO(requests.get(fallback_url).content))
            
        base_img = base_img.resize((1080, 1080))
        base_img = base_img.filter(ImageFilter.GaussianBlur(5)) 
        overlay = Image.new('RGBA', (1080, 1080), (0, 0, 0, 180)) 
        bg_final = Image.alpha_composite(base_img.convert('RGBA'), overlay)
        
    except:
        base_img = Image.new('RGB', (1080, 1080), color='#1a1a2e')
        bg_final = base_img

    # --- 렌더링 루프 (탭 뷰 방식 적용) ---
    fonts = get_fonts()
    if not fonts: st.error("폰트 로딩 실패"); st.stop()
    
    st.markdown(f"### 📸 총 {len(slides)}장의 카드뉴스가 생성되었습니다.")
    
    # [핵심 변경] st.columns -> st.tabs (안정성 확보)
    tab_names = [f"{i+1}면" for i in range(len(slides))]
    tabs = st.tabs(tab_names)
    
    for i, slide in enumerate(slides):
        img = bg_final.copy()
        draw = ImageDraw.Draw(img)
        
        font_cover_title = ImageFont.truetype(BytesIO(fonts['title']), 90)
        font_cover_sub = ImageFont.truetype(BytesIO(fonts['body']), 50)
        font_content = ImageFont.truetype(BytesIO(fonts['body']), 65) 
        font_outro_slogan = ImageFont.truetype(BytesIO(fonts['serif']), 80)
        font_outro_brand = ImageFont.truetype(BytesIO(fonts['body']), 40)
        
        if slide.get("TYPE") == "COVER":
            draw.text((60, 80), "SEGYE BRIEFING", font=font_outro_brand, fill=color_main)
            title_text = slide.get("TEXT", "")
            lines = wrap_text(title_text, font_cover_title, 960, draw)
            start_y = 350
            for line in lines:
                draw.text((60, start_y), line, font=font_cover_title, fill="white")
                start_y += 110
            draw.line((60, start_y+20, 260, start_y+20), fill=color_main, width=12)
            if slide.get("SUB"):
                draw.text((60, start_y+80), slide["SUB"], font=font_cover_sub, fill="#cccccc")

        elif slide.get("TYPE") == "CONTENT":
            draw.text((950, 60), f"{i+1}", font=font_cover_sub, fill="#888888")
            body_text = clean_text_strict(slide.get("TEXT", ""))
            lines = wrap_text(body_text, font_content, 900, draw)
            total_height = len(lines) * 90
            start_y = (1080 - total_height) / 2 
            for line in lines:
                draw.text((90, start_y), line, font=font_content, fill="white")
                start_y += 90
            bar_y_start = (1080 - total_height) / 2
            draw.line((50, bar_y_start, 50, bar_y_start + total_height), fill=color_main, width=10)

        elif slide.get("TYPE") == "OUTRO":
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=font_outro_slogan)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((1080-w)/2, 450), slogan, font=font_outro_slogan, fill=color_main)
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=font_outro_brand)
            w2 = bbox2[2] - bbox2[0]
            draw.text(((1080-w2)/2, 580), brand, font=font_outro_brand, fill="white")
            draw.line((440, 420, 640, 420), fill="white", width=3)
            draw.line((440, 650, 640, 650), fill="white", width=3)

        # 탭 안에 이미지 출력
        with tabs[i]:
            st.image(img, caption=f"Page {i+1}")
import streamlit as st
import google.generativeai as genai
from newspaper import Article, Config
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
from io import BytesIO
import re
import random
import zipfile
import qrcode # ★ QR코드 생성을 위한 라이브러리 (자동 설치됨)

# --- 페이지 설정 ---
st.set_page_config(page_title="One-Click News v5.0", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v5.0 Pro Director Edition)")
st.markdown("### 💎 QR코드 엔딩 & 브랜드 컬러 시스템 & 프로그레스 바 적용")

# --- 폰트 준비 ---
@st.cache_resource
def get_fonts():
    fonts = {}
    try:
        # 제목: Black Han Sans
        fonts['title'] = requests.get("https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf", timeout=10).content
        # 본문: Nanum Gothic Bold
        fonts['body'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", timeout=10).content
        # 명조(엔딩용): Nanum Myeongjo ExtraBold
        fonts['serif'] = requests.get("https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf", timeout=10).content
    except: return None
    return fonts

# --- 디자인 유틸리티 ---
def create_gradient_overlay(width, height, top_opacity=30, bottom_opacity=220):
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

# ★ QR 코드 생성 함수
def generate_qr_code(link, box_size=10, border=2):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img

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

if st.button("🚀 프로급 카드뉴스 제작"):
    if not api_key or not url: st.error("설정 확인 필요"); st.stop()
    
    status = st.empty()
    status.info("📰 기사를 분석하고 디자인을 설계 중입니다...")
    
    title, text, img_url = advanced_scrape(url)
    if len(text) < 50: st.error("본문 추출 실패"); st.stop()

    # --- [AI 프롬프트: 색상 및 구조 기획] ---
    try:
        status.info("🧠 AI가 테마 컬러를 선정하고 QR 코드를 생성합니다...")
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""
        당신은 세계일보의 '크리에이티브 디렉터'입니다.
        
        [기사]
        제목: {title}
        내용: {text[:4000]}
        
        [규칙]
        1. **분량:** 5~8장 사이.
        2. **구조:**
           - HEAD: 15자 이내 핵심 제목
           - DESC: 60자 이내 친절한 설명 (2~3문장)
        3. **컬러 선정 (중요):** 기사 분위기에 맞는 **세련되고 짙은 단색(Solid Color)** 코드를 하나 뽑으세요. 
           - 정치/무거움: #0f172a (Navy), #450a0a (Dark Red)
           - 경제/신뢰: #1e3a8a (Royal Blue), #14532d (Dark Green)
           - 사회/활기: #b45309 (Dark Orange), #7e22ce (Purple)
           - 이 색상은 **마지막 장의 배경색**이자, **본문의 강조색**으로 쓰입니다.
        
        [출력 양식]
        COLOR_MAIN: #Hex
        
        [SLIDE 1]
        TYPE: COVER
        HEAD: [메인 제목]
        DESC: [부제]
        
        [SLIDE 2]
        TYPE: CONTENT
        HEAD: [키워드]
        DESC: [설명]
        
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
        color_main = "#1e3a8a" # Default Navy
        
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
        status.success(f"✅ 기획 완료: 총 {len(slides)}장 / 테마 컬러: {color_main}")
        
    except Exception as e:
        st.error(f"기획 오류: {e}")
        st.stop()

    # --- 이미지 준비 ---
    try:
        # 1. 메인 이미지 (표지~본문용)
        if user_image: base_img = Image.open(user_image)
        elif img_url:
            headers = {'User-Agent': 'Mozilla/5.0'}
            base_img = Image.open(BytesIO(requests.get(img_url, headers=headers, timeout=5).content))
        else:
            base_img = Image.new('RGB', (1080, 1080), color='#1a1a2e')
            
        base_img = base_img.convert('RGB').resize((1080, 1080))
        enhancer = ImageEnhance.Brightness(base_img)
        base_img = enhancer.enhance(0.7) 
        
        gradient = create_gradient_overlay(1080, 1080, top_opacity=40, bottom_opacity=230)
        bg_content = Image.alpha_composite(base_img.convert('RGBA'), gradient)
        
        # 2. 엔딩 배경 (브랜드 단색) - 색상이 안 맞을 경우 대비한 안전장치
        try:
            bg_outro = Image.new('RGB', (1080, 1080), color=color_main)
        except:
            bg_outro = Image.new('RGB', (1080, 1080), color='#1a1a2e')
            color_main = '#FFD700' # 색상 오류시 골드로 대체
            
    except:
        st.error("이미지 처리 실패")
        st.stop()

    # --- QR 코드 생성 ---
    qr_img = generate_qr_code(url, box_size=10, border=1)
    qr_img = qr_img.resize((200, 200)) # 사이즈 조정

    # --- 렌더링 루프 ---
    fonts = get_fonts()
    if not fonts: st.error("폰트 로딩 실패"); st.stop()
    
    st.markdown(f"### 📸 Pro Director Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    for i, slide in enumerate(slides):
        # 배경 선택 (마지막 장은 단색, 나머지는 사진)
        if slide.get("TYPE") == "OUTRO":
            img = bg_outro.copy() # 단색 배경
        else:
            img = bg_content.copy() # 사진 배경
            
        draw = ImageDraw.Draw(img)
        
        # 폰트
        font_head = ImageFont.truetype(BytesIO(fonts['title']), 85)
        font_desc = ImageFont.truetype(BytesIO(fonts['body']), 48)
        font_serif = ImageFont.truetype(BytesIO(fonts['serif']), 90) # 슬로건용
        font_small = ImageFont.truetype(BytesIO(fonts['body']), 30)
        
        # [공통 디자인] 프로그레스 바 (상단)
        progress_width = 1080 * ((i+1) / len(slides))
        draw.rectangle([(0, 0), (progress_width, 15)], fill=color_main)
        
        # [SLIDE 1: COVER]
        if slide.get("TYPE") == "COVER":
            # 브랜드 태그
            draw.rectangle([(50, 60), (350, 120)], fill=color_main)
            draw.text((70, 72), "SEGYE BRIEFING", font=font_small, fill="black" if color_main in ['#FFD700', '#00FFFF'] else "white")
            
            head_text = slide.get("HEAD", "")
            lines = wrap_text(head_text, font_head, 960, draw)
            start_y = 600 - (len(lines) * 50)
            for line in lines:
                draw_text_with_shadow(draw, (60, start_y), line, font_head)
                start_y += 100
            
            if slide.get("DESC"):
                desc_text = slide.get("DESC", "")
                d_lines = wrap_text(desc_text, font_desc, 960, draw)
                dy = start_y + 40
                draw.line((60, dy, 260, dy), fill=color_main, width=8) 
                dy += 50
                for line in d_lines:
                    draw_text_with_shadow(draw, (60, dy), line, font_desc, text_color="#eeeeee")
                    dy += 60

        # [SLIDE 2~N: CONTENT]
        elif slide.get("TYPE") == "CONTENT":
            # 페이지 번호
            draw_text_with_shadow(draw, (950, 60), f"{i+1}", font_small)
            
            # 1. 헤드라인 (포인트 컬러)
            head_text = slide.get("HEAD", "")
            lines = wrap_text(head_text, font_head, 900, draw)
            start_y = 300
            
            # 세로 바 (포인트 컬러)
            draw.rectangle([(60, start_y), (75, start_y + (len(lines)*100) + 20)], fill=color_main)
            
            for line in lines:
                draw_text_with_shadow(draw, (90, start_y), line, font_head)
                start_y += 100
            
            # 2. 설명
            desc_text = clean_text_strict(slide.get("DESC", ""))
            d_lines = wrap_text(desc_text, font_desc, 900, draw)
            dy = start_y + 40
            for line in d_lines:
                draw_text_with_shadow(draw, (90, dy), line, font_desc, text_color="#dddddd")
                dy += 65

        # [SLIDE LAST: OUTRO] (완전히 다른 디자인)
        elif slide.get("TYPE") == "OUTRO":
            # 1. 중앙 슬로건 (명조체)
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=font_serif)
            w = bbox[2] - bbox[0]
            # 배경이 단색이므로 그림자 없이 깔끔하게 흰색으로
            draw.text(((1080-w)/2, 350), slogan, font=font_serif, fill="white")
            
            # 2. 로고 텍스트
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=font_desc)
            w2 = bbox2[2] - bbox2[0]
            draw.text(((1080-w2)/2, 480), brand, font=font_desc, fill="#dddddd")
            
            # 3. 장식 라인
            draw.line((350, 460, 730, 460), fill="white", width=2)
            
            # 4. QR 코드 부착 (하단 중앙)
            # QR 코드 배경 박스 (흰색)
            qr_bg_x = (1080 - 220) // 2
            qr_bg_y = 650
            draw.rectangle([(qr_bg_x, qr_bg_y), (qr_bg_x + 220, qr_bg_y + 220)], fill="white")
            
            # QR 코드 붙여넣기
            img.paste(qr_img, (qr_bg_x + 10, qr_bg_y + 10))
            
            # 안내 문구
            msg = "기사 원문 보러가기"
            bbox3 = draw.textbbox((0, 0), msg, font=font_small)
            w3 = bbox3[2] - bbox3[0]
            draw.text(((1080-w3)/2, 900), msg, font=font_small, fill="white")

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
            
    st.download_button("💾 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_pro_edition.zip", "application/zip", use_container_width=True)
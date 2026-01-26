import streamlit as st
import google.generativeai as genai
from newspaper import Article, Config
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import io
import re
import random
import zipfile
import qrcode
import os
import numpy as np

# --- [설정] 자산 파일명 (반드시 이 이름으로 파일을 넣어주세요) ---
ASSET_CONFIG = {
    "logo_symbol": "segye_symbol.png", # 심볼 (이미지)
    "logo_text": "segye_text.png",     # 텍스트 로고 (이미지)
    "font_title": "Title.ttf",
    "font_body": "Body.ttf",
    "font_serif": "Serif.ttf"
}

# --- 페이지 설정 ---
st.set_page_config(page_title="One-Click News v9.1", page_icon="📰", layout="wide")
st.title("📰 One-Click News (v9.1 Hybrid Logo)")
st.markdown("### 💎 심볼+텍스트 분리형 로고 시스템 적용")

# --- [기능] 로컬 자산 로드 ---
@st.cache_resource
def load_local_assets():
    assets = {}
    
    # 1. 폰트 로드 함수
    def load_font(filename, fallback_url):
        if os.path.exists(filename):
            with open(filename, "rb") as f: return f.read()
        return requests.get(fallback_url).content

    assets['title'] = load_font(ASSET_CONFIG['font_title'], "https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf")
    assets['body'] = load_font(ASSET_CONFIG['font_body'], "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf")
    assets['serif'] = load_font(ASSET_CONFIG['font_serif'], "https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf")

    # 2. 로고 2종 로드 (심볼, 텍스트)
    def load_image(filename, width_target):
        if os.path.exists(filename):
            try:
                img = Image.open(filename).convert("RGBA")
                aspect = img.height / img.width
                return img.resize((width_target, int(width_target * aspect)))
            except: pass
        return None

    # 심볼은 가로 60px, 텍스트 로고는 가로 160px 정도로 리사이징
    assets['symbol'] = load_image(ASSET_CONFIG['logo_symbol'], 60)
    assets['logotxt'] = load_image(ASSET_CONFIG['logo_text'], 160)
    
    return assets

# --- [디자인] 유틸리티 함수 ---

def paste_hybrid_logo(bg_img, symbol, logotxt, x=50, y=50, gap=15):
    """
    HTML/CSS의 flex 배치처럼 심볼과 텍스트를 나란히 붙이는 함수
    """
    # 심볼 붙이기
    if symbol:
        bg_img.paste(symbol, (x, y), symbol)
        next_x = x + symbol.width + gap
    else:
        next_x = x

    # 텍스트 로고 붙이기 (수직 중앙 정렬 보정)
    if logotxt:
        # 심볼 높이의 중간에 텍스트가 오도록 계산
        if symbol:
            center_y = y + (symbol.height // 2)
            txt_y = center_y - (logotxt.height // 2)
        else:
            txt_y = y
        bg_img.paste(logotxt, (next_x, txt_y), logotxt)

def is_color_dark(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6: return False
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 120

def create_glass_box(draw, xy, r, fill=(0,0,0,160)):
    draw.rounded_rectangle(xy, radius=r, fill=fill)

def create_smooth_gradient(width, height):
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        ratio = y / height
        if ratio > 0.4:
            alpha = int(255 * ((ratio - 0.4) / 0.6) ** 1.5)
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return overlay

def draw_text_with_shadow(draw, position, text, font, fill="white", shadow_color="black", offset=(3, 3)):
    x, y = position
    draw.text((x + offset[0], y + offset[1]), text, font=font, fill=shadow_color)
    draw.text((x-1, y), text, font=font, fill=shadow_color)
    draw.text((x+1, y), text, font=font, fill=shadow_color)
    draw.text((x, y-1), text, font=font, fill=shadow_color)
    draw.text((x, y+1), text, font=font, fill=shadow_color)
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

# --- 스크래핑 ---
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
    st.success("✅ 로고(심볼+텍스트)와 폰트가 고정되었습니다.")

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
        [기사] 제목: {title} / 내용: {text[:6000]}
        [규칙]
        1. **총 8장 (Cover 1 + Story 6 + Outro 1)**
        2. **Cover:** HEAD(10자 이내), DESC(40자 이내)
        3. **Story:** HEAD(키워드), DESC(80~100자 내외 충실히). 반복 금지.
        4. **Color:** 기사 분위기에 맞는 짙은 색상(Hex) 1개.
        [출력]
        COLOR_MAIN: #Hex
        [SLIDE 1]
        TYPE: COVER
        HEAD: ...
        DESC: ...
        ...
        [SLIDE 8]
        TYPE: OUTRO
        HEAD: First in, Last out
        DESC: 세상을 보는 눈, 세계일보
        """
        response = model.generate_content(prompt)
        
        slides = []
        curr = {}
        color_main = "#FFD700"
        
        for line in response.text.split('\n'):
            line = line.strip()
            if not line: continue
            if line.startswith("COLOR_MAIN:"): color_main = line.split(":")[1].strip()
            elif "[SLIDE" in line:
                if curr: slides.append(curr)
                curr = {"HEAD": "", "DESC": "", "TYPE": ""}
            elif line.startswith("TYPE:"): curr["TYPE"] = line.split(":")[1].strip()
            elif line.startswith("HEAD:"): curr["HEAD"] = line.split("HEAD:")[1].strip()
            elif line.startswith("DESC:"): curr["DESC"] = line.split("DESC:")[1].strip()
        if curr: slides.append(curr)
        
    except: st.error("기획 실패"); st.stop()

    # --- 자산 로드 ---
    try:
        assets = load_local_assets()
        
        if user_image: base_img = Image.open(user_image)
        elif img_url:
            headers = {'User-Agent': 'Mozilla/5.0'}
            base_img = Image.open(io.BytesIO(requests.get(img_url, headers=headers, timeout=5).content))
        else: base_img = Image.new('RGB', (1080, 1080), color='#1a1a2e')
        base_img = base_img.convert('RGB').resize((1080, 1080))
        
        # 배경 세트 생성
        grad = create_smooth_gradient(1080, 1080)
        bg_cover = base_img.copy()
        bg_cover.paste(grad, (0,0), grad)
        
        bg_blur = base_img.copy()
        bg_blur = bg_blur.filter(ImageFilter.GaussianBlur(15))
        bg_blur = ImageEnhance.Brightness(bg_blur).enhance(0.7)
        
        try: bg_outro = Image.new('RGB', (1080, 1080), color=color_main)
        except: bg_outro = Image.new('RGB', (1080, 1080), color='#1a1a2e')

    except Exception as e: st.error(f"자산 오류: {e}"); st.stop()

    # --- 렌더링 ---
    st.markdown(f"### 📸 Segae Hybrid Logo Edition ({len(slides)} Pages)")
    generated_images = []
    tabs = st.tabs([f"{i+1}면" for i in range(len(slides))])
    
    text_color_title = "#FFFFFF" if is_color_dark(color_main) else color_main

    for i, slide in enumerate(slides):
        if slide['TYPE'] == 'COVER': img = bg_cover.copy()
        elif slide['TYPE'] == 'OUTRO': img = bg_outro.copy()
        else: img = bg_blur.copy()
            
        draw = ImageDraw.Draw(img, 'RGBA')
        
        # 폰트
        ft_head = ImageFont.truetype(io.BytesIO(assets['title']), 95)
        ft_desc = ImageFont.truetype(io.BytesIO(assets['body']), 48)
        ft_small = ImageFont.truetype(io.BytesIO(assets['body']), 30)
        ft_serif = ImageFont.truetype(io.BytesIO(assets['serif']), 90)
        
        # [NEW] 로고 2종(심볼+텍스트) 나란히 붙이기
        if slide['TYPE'] != 'OUTRO':
            # paste_hybrid_logo 함수가 CSS Flex 효과를 냅니다
            paste_hybrid_logo(img, assets.get('symbol'), assets.get('logotxt'), x=50, y=50, gap=15)
            
            # 페이지 번호
            draw.text((950, 60), f"{i+1} / {len(slides)}", font=ft_small, fill="white")

        # [COVER]
        if slide['TYPE'] == 'COVER':
            head = slide.get("HEAD", "")
            desc = slide.get("DESC", "")
            
            d_lines = wrap_text(desc, ft_desc, 980, draw)
            desc_h = len(d_lines) * 60
            curr_y = 1080 - 100 - desc_h 
            for line in d_lines:
                draw_text_with_shadow(draw, (50, curr_y), line, ft_desc, fill="#eeeeee")
                curr_y += 60
            
            curr_y -= (desc_h + 30)
            draw.rectangle([(50, curr_y), (150, curr_y+10)], fill=color_main)
            
            h_lines = wrap_text(head, ft_head, 980, draw)
            head_h = len(h_lines) * 110
            curr_y -= (head_h + 30)
            for line in h_lines:
                draw_text_with_shadow(draw, (50, curr_y), line, ft_head, fill="white", offset=(4,4))
                curr_y += 110

        # [CONTENT]
        elif slide['TYPE'] == 'CONTENT':
            layout = random.choice(['BOX', 'LEFT_BAR', 'QUOTE'])
            head = slide.get("HEAD", "")
            desc = slide.get("DESC", "")
            
            if layout == 'BOX':
                h_lines = wrap_text(head, ft_head, 850, draw)
                d_lines = wrap_text(desc, ft_desc, 850, draw)
                box_h = (len(h_lines)*110) + (len(d_lines)*65) + 120
                start_y = (1080 - box_h) / 2
                
                create_glass_box(draw, (80, start_y, 1000, start_y + box_h), 30)
                
                txt_y = start_y + 50
                for line in h_lines:
                    draw.text((120, txt_y), line, font=ft_head, fill=text_color_title)
                    txt_y += 110
                draw.line((120, txt_y+10, 320, txt_y+10), fill=text_color_title, width=5)
                txt_y += 40
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
                draw.text((80, 250), "“", font=ImageFont.truetype(io.BytesIO(assets['serif']), 400), fill=(255, 255, 255, 30))
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

        # [OUTRO]
        elif slide['TYPE'] == 'OUTRO':
            slogan = "First in, Last out"
            bbox = draw.textbbox((0, 0), slogan, font=ft_serif)
            w = bbox[2] - bbox[0]
            
            outro_color = "white" if is_color_dark(color_main) else "black"
            
            draw.text(((1080-w)/2, 350), slogan, font=ft_serif, fill=outro_color)
            
            brand = "세상을 보는 눈, 세계일보"
            bbox2 = draw.textbbox((0, 0), brand, font=ft_desc)
            w2 = bbox2[2] - bbox2[0]
            draw.text(((1080-w2)/2, 480), brand, font=ft_desc, fill=outro_color)
            
            qr_img = generate_qr_code(url).resize((220, 220))
            qr_x = (1080 - 240) // 2
            qr_y = 650
            draw.rounded_rectangle((qr_x, qr_y, qr_x+240, qr_y+240), radius=20, fill="white")
            img.paste(qr_img, (qr_x+10, qr_y+10))
            
            msg = "기사 원문 보러가기"
            bbox3 = draw.textbbox((0, 0), msg, font=ft_small)
            w3 = bbox3[2] - bbox3[0]
            draw.text(((1080-w3)/2, 910), msg, font=ft_small, fill=outro_color)

        generated_images.append(img)
        with tabs[i]: st.image(img, caption=f"Page {i+1}")

    # --- 다운로드 ---
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for i, img in enumerate(generated_images):
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            zf.writestr(f"card_{i+1:02d}.png", img_byte_arr.getvalue())
    st.download_button("💾 전체 다운로드 (.zip)", zip_buffer.getvalue(), "segye_news_hybrid.zip", "application/zip", use_container_width=True)
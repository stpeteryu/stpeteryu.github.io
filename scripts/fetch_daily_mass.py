#!/usr/bin/env python3
"""
한국천주교주교회의 매일미사 사이트(missa.cbck.or.kr)에서
오늘의 미사 말씀을 스크래핑해서 daily-mass.json으로 저장합니다.
Anthropic API 불필요 — 공식 사이트 직접 파싱.
캐나다 동부 시간(America/Toronto) 기준.
"""

import json, os, re, sys
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup

# ── 날짜 설정 (캐나다 동부 시간) ────────────────────────
eastern  = pytz.timezone('America/Toronto')
today    = datetime.now(eastern)
date_str = today.strftime('%Y-%m-%d')
date_url = today.strftime('%Y%m%d')

print(f"[매일미사] {date_str} 스크래핑 시작")

# ── 페이지 가져오기 ────────────────────────────────────
URL     = f'https://missa.cbck.or.kr/DailyMissa/{date_url}'
HEADERS = {'User-Agent': 'Mozilla/5.0 (parish-website-bot/1.0)'}

try:
    resp = requests.get(URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    print(f"  페이지 로드 성공: {URL}")
except Exception as e:
    print(f"  페이지 로드 실패: {e}")
    sys.exit(1)

soup = BeautifulSoup(resp.text, 'html.parser')

# ── 헬퍼 함수 ─────────────────────────────────────────
COLOR_MAP = {
    '백': '백색', '녹': '녹색', '자': '자주색',
    '홍': '빨간색', '장': '검은색', '금': '금색'
}

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()

def get_section_content(start_h4, max_p=25):
    """h4 이후 다음 h4 전까지 텍스트 줄 수집"""
    lines, node = [], start_h4.next_sibling
    while node and len(lines) < max_p:
        if hasattr(node, 'name'):
            if node.name in ('h2', 'h3', 'h4'):
                break
            t = clean(node.get_text())
            if t:
                lines.append(t)
        node = node.next_sibling
    return lines

def find_h5_ref(h4_tag):
    """h4 다음에 나오는 h5에서 장절(예: 4,1-12) 추출"""
    node = h4_tag.next_sibling
    while node:
        if hasattr(node, 'name'):
            if node.name == 'h5':
                return clean(node.get_text())
            if node.name == 'h4':
                break
        node = node.next_sibling
    return ''

def find_book(lines):
    """'▥ 사도행전의 말씀입니다.' 또는 '✠ 요한이 전한' 에서 책 이름 추출"""
    for line in lines:
        m = re.search(r'[▥]\s+(.+?)\s*의\s+말씀', line)
        if m:
            return m.group(1).strip()
        m = re.search(r'[✠]\s+(.+?)\s*(?:이|가)\s+전한', line)
        if m:
            return m.group(1).strip()
    return ''

def find_subtitle(lines):
    """<소제목> 형태 추출"""
    for line in lines:
        if re.match(r'^[<〈].+[>〉]$', line):
            return re.sub(r'^[<〈]|[>〉]$', '', line).strip()
    return ''

def body_text(lines, chapter='', book='', max_lines=10):
    """본문 줄만 추려서 합치기 (기호·메타 줄 제외)"""
    skip = {chapter, book + '의 말씀입니다.', '주님의 말씀입니다.',
            '하느님, 감사합니다.', '그리스도님, 찬미합니다.'}
    result = []
    for line in lines:
        if line in skip:
            continue
        if re.match(r'^[▥✠◎○⊕\d]', line):
            continue
        if re.match(r'^[<〈].+[>〉]$', line):
            continue
        result.append(line)
        if len(result) >= max_lines:
            break
    return ' '.join(result)

def get_antiphon(lines):
    """◎ 응답 구절"""
    for line in lines:
        if line.startswith('◎'):
            t = line.lstrip('◎').strip()
            if t and t not in ('알렐루야.',):
                return t
    return ''

# ── 섹션 맵 구성 ──────────────────────────────────────
section_map = {}
for h4 in soup.find_all('h4'):
    key = clean(h4.get_text()).lower()
    section_map[key] = h4

def find_section(keyword):
    for k, v in section_map.items():
        if keyword in k:
            return v
    return None

# ── 전례일 ────────────────────────────────────────────
liturgical_day = ''
liturgical_color_name = ''
h3 = soup.find('h3')
if h3:
    raw = clean(h3.get_text())
    m = re.match(r'\[([가-힣])\]\s*(.+)', raw)
    if m:
        liturgical_day = m.group(2).strip()
        liturgical_color_name = COLOR_MAP.get(m.group(1), m.group(1))
    else:
        liturgical_day = raw
print(f"  전례일: {liturgical_day} ({liturgical_color_name})")

# ── 제1독서 ───────────────────────────────────────────
first_reading = None
h4 = find_section('제1독서')
if h4:
    lines    = get_section_content(h4)
    book     = find_book(lines)
    chapter  = find_h5_ref(h4)
    ref      = f"{book} {chapter}".strip() if book else chapter
    subtitle = find_subtitle(lines)
    text     = body_text(lines, chapter, book)
    first_reading = {'ref': ref, 'subtitle': subtitle, 'text': text}
    print(f"  제1독서: {ref}")

# ── 화답송 ────────────────────────────────────────────
psalm = None
h4 = find_section('화답송')
if h4:
    ref_raw  = re.sub(r'^화답송', '', clean(h4.get_text())).strip()
    lines    = get_section_content(h4)
    antiphon = get_antiphon(lines)
    psalm    = {'ref': ref_raw, 'antiphon': antiphon}
    print(f"  화답송: {ref_raw[:35]}")

# ── 제2독서 (주일) ────────────────────────────────────
second_reading = None
h4 = find_section('제2독서')
if h4:
    lines    = get_section_content(h4)
    book     = find_book(lines)
    chapter  = find_h5_ref(h4)
    ref      = f"{book} {chapter}".strip() if book else chapter
    subtitle = find_subtitle(lines)
    text     = body_text(lines, chapter, book)
    second_reading = {'ref': ref, 'subtitle': subtitle, 'text': text}
    print(f"  제2독서: {ref}")

# ── 복음 ──────────────────────────────────────────────
gospel = None
# '복음 환호송' 제외하고 순수 '복음' 섹션 찾기
h4_gospel = None
for k, v in section_map.items():
    if k.strip() == '복음':
        h4_gospel = v
        break
if not h4_gospel:
    h4_gospel = find_section('복음')
    if h4_gospel and '환호' in clean(h4_gospel.get_text()):
        h4_gospel = None

if h4_gospel:
    lines     = get_section_content(h4_gospel, max_p=35)
    book      = find_book(lines)
    chapter   = find_h5_ref(h4_gospel)
    ref       = f"{book} {chapter}".strip() if book else chapter
    subtitle  = find_subtitle(lines)
    key_verse = subtitle or ''
    text      = body_text(lines, chapter, book, max_lines=12)
    gospel    = {'ref': ref, 'key_verse': key_verse, 'text': text}
    print(f"  복음: {ref}")

# ── 오늘의 묵상 ───────────────────────────────────────
reflection = None
h4 = find_section('오늘의 묵상')
if h4:
    lines = get_section_content(h4, max_p=4)
    if lines:
        reflection = lines[0]
        print(f"  묵상: {reflection[:50]}...")

# ── JSON 저장 ─────────────────────────────────────────
data = {
    'date':              date_str,
    'liturgical_day':    liturgical_day,
    'liturgical_color':  liturgical_color_name,
    'source_url':        URL,
    'first_reading':     first_reading,
    'psalm':             psalm,
    'second_reading':    second_reading,
    'gospel':            gospel,
    'reflection':        reflection,
}

# 스크립트가 scripts/ 안에 있으므로 한 단계 위가 저장소 루트
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out  = os.path.join(root, 'daily-mass.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n✅ 저장 완료 → {out}")

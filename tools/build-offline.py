#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""오프라인 단일 파일 빌드 — index.html + assets/ → dist/before-it-blows-offline.html

인터넷도 assets/ 폴더도 없이, html 파일 하나만 복사해 더블클릭으로 실행하는 배포판
(USB·메일·오프라인 전시·수업용)을 만든다. 표준 라이브러리만 쓴다.

  python3 tools/build-offline.py           # 빌드
  python3 tools/build-offline.py --check   # 커밋된 결과물이 최신인지 확인 (다르면 exit 1)

하는 일 (index.html 의 로직은 건드리지 않는다 — 넣기만 한다):
  1. @font-face 의 url('assets/fonts/*.woff2') 4개 → data:font/woff2;base64
  2. <meta charset> 바로 뒤에 '생성 파일' 표기 + 폰트 라이선스(SIL OFL 1.1) 원문 주석
  3. 본 <script> 바로 앞에 이미지 23장·BGM 2곡의 base64 블록 + 이를 모아
     window.BIB_OFFLINE = {img:{...}, bgm:{...}} 를 만드는 작은 로더
     — index.html 의 offURL() 이 이것을 blob: URL 로 바꿔 쓰고, CDN 폴백은 끈다.

index.html·assets 를 고쳤으면 다시 돌린다. 기대한 패턴이 하나라도 없으면 아무것도
쓰지 않고 실패한다(조용히 assets/ 를 참조하는 '가짜 단일 파일'이 나오는 것을 막는다).
"""
import argparse, base64, hashlib, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'index.html'
OUT = ROOT / 'dist' / 'before-it-blows-offline.html'
SEAM = 'window.BIB_OFFLINE'
LICENSES = ['assets/fonts/OFL-NanumMyeongjo.txt', 'assets/fonts/OFL-NotoSansKR.txt']


def die(msg):
    print('build-offline: ' + msg, file=sys.stderr)
    sys.exit(2)


def need(cond, msg):
    if not cond:
        die(msg)


def magic_ok(kind, data):
    if kind == 'webp':
        return data[:4] == b'RIFF' and data[8:12] == b'WEBP'
    if kind == 'mp3':
        return data[:3] == b'ID3' or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    if kind == 'woff2':
        return data[:4] == b'wOF2'
    return False


def read_asset(rel, kind):
    p = ROOT / rel
    need(p.is_file(), f'에셋이 없다: {rel}')
    data = p.read_bytes()
    need(magic_ok(kind, data), f'{kind} 파일이 아니다(손상·LFS 포인터?): {rel}')
    return data


def b64(data):
    return base64.b64encode(data).decode('ascii')


def build():
    raw = SRC.read_bytes()
    html = raw.decode('utf-8')

    # ---------- 전제 조건 ----------
    need(html.count('<script') == 1, 'index.html 의 <script> 가 1개가 아니다 — 삽입 위치를 특정할 수 없다')
    need(SEAM in html, f'index.html 에 {SEAM} 연결부가 없다 — 넣어도 쓰이지 않는다')
    meta = '<meta charset="UTF-8">'
    need(html.count(meta) == 1, f'{meta} 가 정확히 1개가 아니다')

    m = re.search(r'const CDN = \{(.*?)\n\};', html, re.S)
    need(m, 'const CDN = {...}; 블록을 찾지 못했다')
    img_keys = re.findall(r'^\s*(\w+)\s*:\s*"', m.group(1), re.M)
    files = sorted(p.stem for p in (ROOT / 'assets').glob('*.webp'))
    need(sorted(img_keys) == files,
         f'CDN 키와 assets/*.webp 가 어긋난다 — 키에만: {sorted(set(img_keys) - set(files))}, '
         f'파일에만: {sorted(set(files) - set(img_keys))}')

    bgm_keys = sorted(set(re.findall(r'\bbgm:"(\w+)"', html)) | set(re.findall(r"ensure\('(\w+)'\)", html)))
    need(bgm_keys, 'bgm 키를 찾지 못했다')

    font_re = re.compile(r"url\('(assets/fonts/([\w.-]+\.woff2))'\)")
    fonts = font_re.findall(html)
    need(len(fonts) == 4, f"url('assets/fonts/*.woff2') 가 4개가 아니다: {len(fonts)}")

    # ---------- 변환 ----------
    out = font_re.sub(lambda mm: "url('data:font/woff2;base64," + b64(read_asset(mm.group(1), 'woff2')) + "')", html)

    lic = '\n\n'.join(f'----- {Path(r).name} -----\n' + (ROOT / r).read_text(encoding='utf-8').strip() for r in LICENSES)
    header = (
        '\n<!--\n'
        '  터지기 전에 — 가스안전 사건파일 · 오프라인 단일 파일판\n'
        '  이 파일은 tools/build-offline.py 가 index.html + assets/ 로 생성했다. 직접 고치지 말 것.\n'
        f'  원본 index.html sha256 {hashlib.sha256(raw).hexdigest()}\n'
        '  내장 글꼴(나눔명조 700/800, Noto Sans KR 400/700 서브셋)은 SIL Open Font License 1.1 —\n'
        '  원문을 아래에 그대로 싣는다.\n\n'
        + lic + '\n-->'
    )
    for bad in ('<!--', '-->', '--!>'):
        need(bad not in lic, f'라이선스 원문에 {bad!r} 가 있어 HTML 주석이 깨진다')
    out = out.replace(meta, meta + header, 1)

    payload = {
        'img': {k: b64(read_asset(f'assets/{k}.webp', 'webp')) for k in img_keys},
        'bgm': {k: b64(read_asset(f'assets/bgm/{k}.mp3', 'mp3')) for k in bgm_keys},
    }
    # base64 는 JS 문자열 리터럴이 아니라 실행되지 않는 text/plain 블록에 싣는다 — JS 파서를
    # 거치지 않아 시작이 빠르다(CPU 4배 감속 실측: 타이틀 이미지 2.06s → 1.39s, 디코드 개선 포함).
    # 작은 로더가 이를 모아 window.BIB_OFFLINE 을 만들고 블록은 DOM 에서 걷어 낸다.
    # base64 알파벳에는 < 가 없으므로 </script>·<!-- 가 끼어들 수 없다.
    blocks = ''.join(f'<script type="text/plain" id="bib-{kind}-{k}">{v}</script>\n'
                     for kind in ('img', 'bgm') for k, v in payload[kind].items())
    loader = ('<script>' + SEAM + '={img:{},bgm:{}};'
              "document.querySelectorAll('script[type=\"text/plain\"][id^=\"bib-\"]').forEach(function(e){"
              "var p=e.id.split('-');" + SEAM + "[p[1]][p[2]]=e.textContent;e.remove();});</script>\n")
    i = out.index('<script')
    out = out[:i] + blocks + loader + out[i:]

    # ---------- 사후 조건 ----------
    # JS 의 'assets/...' 문자열은 BIB_OFFLINE 이 없을 때의 분기라 남아도 쓰이지 않는다(런타임 검사 대상).
    need("url('assets/" not in out, "CSS 의 url('assets/...') 참조가 남았다")
    need(out.index(meta) < 1024, '<meta charset> 이 첫 1024바이트 밖이다 — file:// 에서 한글이 깨진다')
    nblk = len(payload['img']) + len(payload['bgm'])
    need(out.count('<script') == 1 + nblk + 1, f'<script> 가 본문 1 + 데이터 {nblk} + 로더 1 개가 아니다')
    data = out.encode('utf-8')
    need(8_000_000 < len(data) < 20_000_000, f'크기가 이상하다: {len(data):,} B')
    sizes = {
        '이미지': sum(len(v) for v in payload['img'].values()),
        'BGM': sum(len(v) for v in payload['bgm'].values()),
        '폰트': sum(len(b64(read_asset(r, 'woff2'))) for r, _ in fonts),
    }
    return data, len(img_keys), bgm_keys, sizes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true', help='결과물이 최신인지 확인만 한다')
    ap.add_argument('--out', type=Path, default=OUT)
    a = ap.parse_args()
    data, nimg, bgm, sizes = build()
    if a.check:
        cur = a.out.read_bytes() if a.out.is_file() else b''
        if cur != data:
            print(f'{a.out.relative_to(ROOT)} 가 최신이 아니다 — python3 tools/build-offline.py 로 다시 만든다')
            return 1
        print(f'{a.out.relative_to(ROOT)} 최신 ({len(data):,} B)')
        return 0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(data)
    print(f'{a.out.relative_to(ROOT)}  {len(data) / 1e6:.2f} MB  sha256 {hashlib.sha256(data).hexdigest()[:16]}')
    print(f'  이미지 {nimg}장 {sizes["이미지"] / 1e6:.2f} MB · BGM {len(bgm)}곡({", ".join(bgm)}) '
          f'{sizes["BGM"] / 1e6:.2f} MB · 폰트 4벌 {sizes["폰트"] / 1e6:.2f} MB (base64 기준)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

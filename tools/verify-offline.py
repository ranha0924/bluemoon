#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""오프라인 단일 파일판(dist/before-it-blows-offline.html) 자동 검증.

결과물을 빈 임시 폴더에 '혼자' 복사해 file:// 로 연다 — 브라우저는 오프라인 +
DNS 차단 상태라, assets/ 나 인터넷에 기대는 곳이 하나라도 있으면 여기서 깨진다.
서버가 필요 없다(이 파일만큼은 file:// 가 실제 사용 환경이다).

  python3 tools/build-offline.py --check && python3 tools/verify-offline.py

O1 최신성   O2 에셋(이미지 23장·폰트 4면·BGM blob 재생)   O3 전체 플레이
(사건 2개 × 표준/빠른 — 단서·증언·3D 발견·추리·재현 등급 무영향·엔딩)
O4 임명장 PNG   O5 위생(페이지 외 요청 0 · 실패 요청 0 · 콘솔 에러 0)
"""
import shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist' / 'before-it-blows-offline.html'
CH = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
OK, BAD = [], []


def check(name, cond, extra=''):
    (OK if cond else BAD).append(name)
    print(('  OK  ' if cond else '  FAIL') + ' ' + name + ('' if cond else f'  ← {extra}'))


def section(t): print(f'[{t}]')
def active(pg): return pg.evaluate("document.querySelector('.screen.active').id")


def adv(pg):
    for _ in range(200):
        if active(pg) != 'scr-dialog': return
        pg.keyboard.press('Enter'); pg.wait_for_timeout(15)


def play(pg, url, idx, fast):
    pg.goto(f'{url}?fast={int(fast)}'); pg.wait_for_timeout(400)
    pg.click('#scr-title .btn'); pg.click(f'#caseGrid .case-card >> nth={idx}')
    tag = f'{pg.evaluate("G.caseKey")}/{"빠른" if fast else "표준"}'
    adv(pg)
    for ri, rk in enumerate(pg.evaluate('Object.keys(G.C.ROOMS)')):
        pg.click(f'#hubGrid .room-card >> nth={ri}')
        spots = pg.evaluate(f"G.C.ROOMS['{rk}'].spots.map(s=>s.inspect?'i':s.clue?'c':'')")
        for si in [i for i, s in enumerate(spots) if s == 'c']:
            pg.click(f'#spots .spot-btn >> nth={si}'); adv(pg)
        for si in [i for i, s in enumerate(spots) if s == 'i']:
            pg.click(f'#spots .spot-btn >> nth={si}'); pg.wait_for_timeout(250)
            if active(pg) != 'scr-inspect': continue
            f0 = pg.evaluate('INSPECT.found')
            for _ in range(40):
                pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(25)
                if pg.evaluate('INSPECT.found'): break
            check(f'{tag} 3D 조사 — 방향키로만 발견', not f0 and pg.evaluate('INSPECT.found'))
            pg.click('#scr-inspect .btn')
        pg.click('#roomBack')
    check(f'{tag} 단서 전부', pg.evaluate('G.clues.size===Object.keys(G.C.CLUES).length'))
    for _ in range(2):   # 증언으로 열리는 질문까지
        for pi, pk in enumerate(pg.evaluate('Object.keys(G.C.PEOPLE)')):
            pg.click('#talkMenuBtn'); pg.click(f'#hubGrid .room-card >> nth={pi}')
            for qi in range(pg.evaluate(f"G.C.PEOPLE['{pk}'].qs.length")):
                if not pg.evaluate(f"document.querySelectorAll('#talkQs .q-btn')[{qi}].classList.contains('locked')"):
                    pg.click(f'#talkQs .q-btn >> nth={qi}'); pg.keyboard.press('Escape')
            pg.click('#talkBack'); pg.click('#talkMenuBtn')
    check(f'{tag} 지정 증언 확보', pg.evaluate('G.testis.has(G.C.needTesti)'))
    pg.click('#deduceBtn'); adv(pg)
    n = pg.evaluate('G.DQ.length')
    check(f'{tag} 추리 {n}문항', active(pg) == 'scr-deduce' and n == (3 if fast else 4))
    for _ in range(n):
        pg.keyboard.press(str(pg.evaluate('G.DQ[G.deduceIdx].ans') + 1)); pg.wait_for_timeout(1750)
    acts = pg.evaluate('G.C.SIM.actions.map(a=>!!a.ok)')
    w0 = pg.evaluate('[G.wrong,G.hearts]')
    if False in acts:
        pg.keyboard.press(str(acts.index(False) + 1)); pg.wait_for_timeout(80)
    check(f'{tag} 사고 재현 — 오답이 등급에 무영향', active(pg) == 'scr-sim' and pg.evaluate('[G.wrong,G.hearts]') == w0)
    for i, ok in enumerate(acts):
        if ok: pg.keyboard.press(str(i + 1)); pg.wait_for_timeout(80)
    pg.wait_for_timeout(2600); adv(pg)
    check(f'{tag} 엔딩 도달', active(pg) == 'scr-end')
    bg = pg.evaluate('(()=>{const a=BGM.cur; return a&&[a.src.slice(0,5), !a.error, a.duration>100, a.currentTime>1, !a.paused]})()')
    check(f'{tag} BGM 내장본 재생', bg == ['blob:', True, True, True, True], bg)
    broken = pg.evaluate("[...document.images].filter(i=>i.getAttribute('src')&&i.complete&&i.naturalWidth===0).map(i=>i.id||i.dataset.k)")
    check(f'{tag} 깨진 <img> 없음', not broken, broken)


def main():
    section('O1 최신성')
    r = subprocess.run([sys.executable, str(ROOT / 'tools/build-offline.py'), '--check'], capture_output=True, text=True)
    check('build-offline.py --check', r.returncode == 0, (r.stdout + r.stderr).strip())
    if not DIST.is_file():
        print('결과물이 없다 — python3 tools/build-offline.py'); return 2

    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix='bib-offline-'))
    lone = tmp / DIST.name
    shutil.copy(DIST, lone)
    url = lone.as_uri()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CH, args=[
                '--autoplay-policy=no-user-gesture-required', '--host-resolver-rules=MAP * ~NOTFOUND'])
            ctx = b.new_context(viewport={'width': 1280, 'height': 800}, offline=True, accept_downloads=True)
            pg = ctx.new_page()
            reqs, failed, errs = [], [], []
            pg.on('request', lambda q: reqs.append(q.url))
            pg.on('requestfailed', lambda q: failed.append(f'{q.url[:80]} {q.failure}'))
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)

            section('O2 에셋')
            pg.goto(url); pg.wait_for_timeout(800)
            ws = pg.evaluate("""Promise.all(Object.keys(IMG).map(k=>new Promise(r=>{const i=new Image();
                i.onload=()=>r(IMG[k].startsWith('blob:')&&i.naturalWidth>0); i.onerror=()=>r(false); i.src=IMG[k];})))""")
            check(f'이미지 {len(ws)}장 — 전부 내장 blob 에서 디코드', len(ws) == 23 and all(ws))
            faces = pg.evaluate("""(async()=>{ for(const f of ['700 16px "Nanum Myeongjo"','800 16px "Nanum Myeongjo"',
                '400 16px "Noto Sans KR"','700 16px "Noto Sans KR"']) await document.fonts.load(f,'가').catch(()=>{});
                return [...document.fonts].map(f=>f.status); })()""")
            check(f'폰트 4면 loaded {faces}', faces == ['loaded'] * 4)
            check('데이터 블록은 읽은 뒤 DOM 에서 제거', pg.evaluate("document.querySelectorAll('script[type=\"text/plain\"]').length===0"))

            section('O3 전체 플레이')
            for idx in (0, 1):
                for fast in (False, True):
                    play(pg, url, idx, fast)

            section('O4 임명장')
            with pg.expect_download() as dl: pg.click('#certBtn')
            head = Path(dl.value.path()).read_bytes()[:24]
            wh = (int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big'))
            check(f'임명장 PNG {wh}', head[:8] == b'\x89PNG\r\n\x1a\n' and wh == (1500, 2120))

            section('O5 위생')
            other = [u for u in reqs if not u.startswith(('blob:', 'data:')) and u.split('?')[0] != url]
            check('페이지 외 요청 0건', not other, other[:5])
            check('실패 요청 0건', not failed, failed[:5])
            check('콘솔 에러 0건', not errs, errs[:5])
            b.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'\n통과 {len(OK)} / 실패 {len(BAD)}')
    if BAD:
        for x in BAD: print('  FAIL ' + x)
        return 1
    print('PASS — 오프라인 단일 파일 검증 전부 통과')
    return 0


if __name__ == '__main__':
    sys.exit(main())

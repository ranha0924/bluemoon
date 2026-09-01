#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게임 내장 학급 설문(#survey 오버레이) 자동 검증 — V1~V12.

survey.html 시절의 스위트를 내장판 기준으로 재작성했다.
로컬 서버가 필요하다:  python3 -m http.server 8899  (저장소 루트에서)
"""
import json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CH = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
BASE = 'http://localhost:8899/index.html'
OK, BAD = [], []

def check(name, cond, extra=''):
    (OK if cond else BAD).append(name + (f' — {extra}' if extra and not cond else ''))
    print(('  OK  ' if cond else '  FAIL') + ' ' + name + ('' if cond else f'  ← {extra}'))

def section(t): print(f'[{t}]')

def main():
    try:
        urllib.request.urlopen('http://localhost:8899/index.html', timeout=3)
    except Exception:
        print('로컬 서버가 없다 — 저장소 루트에서: python3 -m http.server 8899'); return 2

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CH, headless=True)

        # ---------- V1 로비 진입 ----------
        section('V1 로비 [학급 설문] 진입')
        ctx = b.new_context(viewport={'width': 1280, 'height': 800})
        pg = ctx.new_page()
        errs, ext = [], []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('request', lambda r: ext.append(r.url) if 'localhost' not in r.url and not r.url.startswith('data:') else None)
        pg.goto(BASE); pg.wait_for_timeout(900)
        pg.evaluate("localStorage.clear()")
        pg.click("text=사건 파일 열기"); pg.wait_for_timeout(300)
        pg.click("#scr-lobby >> text=학급 설문"); pg.wait_for_timeout(350)
        check('로비 버튼 → 오버레이 열림', pg.evaluate("SV.isOpen()"))
        check('입구 화면 표시', pg.evaluate("!document.getElementById('sv-landing').hidden"))
        pg.click("#survey >> text=닫기 — 게임으로 돌아가기"); pg.wait_for_timeout(250)
        check('닫기 → 게임 복귀(로비 유지)', pg.evaluate("!SV.isOpen() && document.querySelector('.screen.active').id==='scr-lobby'"))

        # ---------- V2 딥링크 ----------
        section('V2 ?survey 딥링크')
        pg.goto(BASE + '?survey=pre'); pg.wait_for_timeout(800)
        check('?survey=pre → 사전 폼', pg.evaluate("SV.isOpen() && !SV.$('sv-form').hidden && SV.mode==='pre'"))
        pg.goto(BASE + '?survey=post'); pg.wait_for_timeout(800)
        check('?survey=post → 사후 폼', pg.evaluate("SV.isOpen() && !SV.$('sv-form').hidden && SV.mode==='post'"))
        pg.goto(BASE + '?survey=1'); pg.wait_for_timeout(800)
        check('?survey=1 → 입구', pg.evaluate("SV.isOpen() && !SV.$('sv-landing').hidden"))
        pg.goto(BASE + '?fast=1&survey=pre'); pg.wait_for_timeout(800)
        check('?fast 와 조합', pg.evaluate("SV.isOpen() && G.fast===true"))

        def fill(pg, answers, sid='10132', name='한세인'):
            pg.evaluate(f"SV.$('inId').value='{sid}'; SV.$('inName').value='{name}'")
            for qi, v in enumerate(answers):
                if v: pg.click(f"#qList fieldset >> nth={qi} >> .opt >> nth={v-1}")

        # ---------- V3 사전 무유출 ----------
        section('V3 사전 제출·무유출')
        pg.goto(BASE + '?survey=pre'); pg.wait_for_timeout(800)
        pg.evaluate("localStorage.clear()")
        fill(pg, [1, 1, 1, 1, 1])
        pg.click("#svSubmit"); pg.wait_for_timeout(350)
        check('사전 완료 화면', pg.evaluate("!SV.$('sv-pre-done').hidden"))
        txt = pg.evaluate("SV.$('sv-pre-done').innerText")
        check('점수·정오 어휘 무유출', not re.search(r'점수|정답|맞았|채점|/\s*5', txt), txt[:60])
        saved = pg.evaluate("JSON.parse(localStorage.getItem('hansein.survey.v1'))")
        check('사전 저장(a·t)', bool(saved and saved.get('pre') and saved['pre']['a'] == [1, 1, 1, 1, 1]))

        # ---------- V4 사후 채점·델타·요약 ----------
        section('V4 사후 채점')
        pg.click("#survey >> text=게임 하러 가기"); pg.wait_for_timeout(250)
        pg.evaluate("SV.open('post')"); pg.wait_for_timeout(350)
        fill(pg, [2, 3, 3, 3, 1])          # 4개 정답 + 5번 오답
        pg.click("#scFun .opt >> nth=4"); pg.click("#scRec .opt >> nth=3")
        pg.evaluate("SV.$('inMemo').value='보관은 40도 이하'")
        pg.click("#svSubmit"); pg.wait_for_timeout(400)
        check('결과 화면', pg.evaluate("!SV.$('sv-result').hidden"))
        check('점수 4/5', pg.evaluate("SV.$('scoreN').textContent") == '4')
        chip = pg.evaluate("SV.$('deltaChip').innerText")
        check('사전 대비 델타', '사전 0/5' in chip and '사후 4/5' in chip and '+4' in chip, chip)
        summ = pg.evaluate("SV.$('sumText').value")
        check('요약문 형식', ('한세인(10132)' in summ and '재미 5' in summ and '추천 4' in summ and '기억:' in summ), summ)
        check('OX 문자열', re.search(r'[OX]{5}→[OX]{5}', summ) is not None, summ)
        bad_rows = pg.evaluate("document.querySelectorAll('#rList .r-item.bad').length")
        check('오답 해설 1건 표시', bad_rows == 1)
        pg.click("#copyBtn"); pg.wait_for_timeout(300)
        check('복사 시도 무예외(토스트)', pg.evaluate("SV.$('svToast').style.display") == 'block')

        # ---------- V5 미응답 검증 ----------
        section('V5 미응답 검증')
        pg.evaluate("SV.open('post')"); pg.wait_for_timeout(300)
        fill(pg, [1, 1, 0, 1, 1])
        pg.click("#svSubmit"); pg.wait_for_timeout(300)
        check('빈 문항 강조', pg.evaluate("document.querySelectorAll('#qList fieldset')[2].classList.contains('miss')"))
        fill(pg, [0, 0, 3, 0, 0])
        pg.click("#svSubmit"); pg.wait_for_timeout(300)
        check('소감 미응답 검증', pg.evaluate("document.querySelector('#svExtra fieldset[data-scale]').classList.contains('miss')"))

        # ---------- V6 리셋 ----------
        section('V6 리셋')
        pg.evaluate("SV.go('sv-landing')"); pg.wait_for_timeout(200)
        pg.click("#landReset"); pg.wait_for_timeout(250)
        check('저장 삭제', pg.evaluate("localStorage.getItem('hansein.survey.v1')") is None)
        check('기록 표시 숨김', pg.evaluate("SV.$('landStat').hidden && SV.$('landReset').hidden"))

        # ---------- V8 키보드 격리·Esc ----------
        section('V8 키보드 격리')
        pg.goto(BASE); pg.wait_for_timeout(800)
        pg.evaluate("G.startCase('case1'); clearInterval(G._tw); G._tw=null; G.dlgQueue=[]; G.dlgDone=null;"
                    "G.clues=new Set(Object.keys(G.C.CLUES)); G.testis=new Set(['t1']); G.deduceIdx=0;"
                    "G.DQ=G.C.DEDUCE; G.show('scr-deduce'); G.renderDeduce()")
        pg.wait_for_timeout(250)
        pg.evaluate("SV.open()"); pg.wait_for_timeout(250)
        before = pg.evaluate("[G.hearts, G.wrong, G.deduceIdx]")
        for k in '1234':
            pg.keyboard.press(k); pg.wait_for_timeout(80)
        check('설문 열림 중 1~4 격리', pg.evaluate("[G.hearts, G.wrong, G.deduceIdx]") == before)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(250)
        check('Esc 로 닫힘', pg.evaluate("!SV.isOpen()"))

        # ---------- V9 모바일 오버레이 ----------
        section('V9 모바일 390px')
        pg.set_viewport_size({'width': 390, 'height': 780})
        pg.evaluate("SV.open('post')"); pg.wait_for_timeout(350)
        no_h = pg.evaluate("SV.$('survey').scrollWidth <= SV.$('survey').clientWidth + 1")
        check('가로 스크롤 없음', no_h)
        tap = pg.evaluate("Math.min(...[...document.querySelectorAll('#survey .sv-btn,#survey .opt')].filter(e=>e.offsetParent!==null).map(e=>e.getBoundingClientRect().height))")
        check('터치 타깃 44px+', tap >= 43.5, str(tap))
        pg.set_viewport_size({'width': 1280, 'height': 800})

        check_errs = list(errs); ctx.close()

        # ---------- V10 저장 차단 환경 ----------
        section('V10 localStorage 차단')
        ctx2 = b.new_context(viewport={'width': 1280, 'height': 800})
        pg2 = ctx2.new_page()
        errs2 = []
        pg2.on('pageerror', lambda e: errs2.append(str(e)))
        pg2.add_init_script("""Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})""")
        pg2.goto(BASE + '?survey=pre'); pg2.wait_for_timeout(900)
        fill(pg2, [2, 3, 3, 3, 3])
        pg2.click("#svSubmit"); pg2.wait_for_timeout(350)
        check('차단 환경 사전 완료+경고', pg2.evaluate("!SV.$('sv-pre-done').hidden && !SV.$('preSaveWarn').hidden"))
        pg2.evaluate("SV.open('post')"); pg2.wait_for_timeout(300)
        fill(pg2, [2, 3, 3, 3, 3])
        pg2.click("#scFun .opt >> nth=4"); pg2.click("#scRec .opt >> nth=4")
        pg2.click("#svSubmit"); pg2.wait_for_timeout(350)
        check('차단 환경 사후 채점(메모리 폴백 5/5)', pg2.evaluate("SV.$('scoreN').textContent") == '5')
        check('차단 환경 pageerror 0', not errs2, '; '.join(errs2[:2]))
        ctx2.close()

        # ---------- V12 file:// ----------
        section('V12 file://')
        ctx3 = b.new_context(viewport={'width': 1280, 'height': 800})
        pg3 = ctx3.new_page()
        errs3 = []
        pg3.on('pageerror', lambda e: errs3.append(str(e)))
        pg3.goto('file://' + str(ROOT / 'index.html') + '?survey=1'); pg3.wait_for_timeout(1200)
        check('file:// 오버레이 열림', pg3.evaluate("SV.isOpen()"))
        check('file:// 서브셋 폰트 로드', pg3.evaluate("document.fonts.check('400 16px \\'Noto Sans KR\\'')"))
        check('file:// pageerror 0', not errs3, '; '.join(errs3[:2]))
        ctx3.close()
        b.close()

    # ---------- V7 서브셋 커버리지 (렌더 문자) ----------
    section('V7 서브셋 커버리지')
    from fontTools.ttLib import TTFont
    html = (ROOT / 'index.html').read_text(encoding='utf-8')
    m = re.search(r'<div id="survey">.*?<div id="svToast"', html, re.S)
    qs = re.search(r'QS:\s*\[.*?\n  \],', html, re.S)
    text = (m.group(0) if m else '') + (qs.group(0) if qs else '')
    text = re.sub(r'<[^>]+>', '', text)
    chars = {c for c in text if ord(c) > 0x7E}
    # 본문(Noto)이 설문의 전 텍스트를 담당하고, 명조는 섹션 제목·숫자 장식에만 쓰인다.
    # ℃ 처럼 명조 원본에 글리프가 없는 문자는 명조 서브셋에 들어갈 수 없지만
    # 명조 문맥에서 렌더되지 않으므로 폰트별 사용 문맥으로 나눠 검사한다.
    noto = set()
    for w in ['NotoSansKR-400', 'NotoSansKR-700']:
        noto |= set(map(chr, TTFont(str(ROOT / f'assets/fonts/{w}.subset.woff2')).getBestCmap()))
    miss_body = chars - noto
    check('설문 본문 글자 전부 Noto 서브셋에 존재', not miss_body, ''.join(sorted(miss_body))[:40])
    nm = set(map(chr, TTFont(str(ROOT / 'assets/fonts/NanumMyeongjo-700.subset.woff2')).getBestCmap()))
    sec_text = '문항 다시 보기 플레이 소감 내 소감 결과 요약 제출 터지기 전에 OX0123456789.'
    miss_nm = {c for c in sec_text if ord(c) > 0x20} - nm
    check('명조 문맥 글자(섹션 제목·숫자) 서브셋에 존재', not miss_nm, ''.join(sorted(miss_nm))[:40])

    # ---------- V11 위생 ----------
    section('V11 위생')
    check('콘솔 에러 0', not check_errs, '; '.join(check_errs[:2]))
    check('외부 요청 0', not ext, '; '.join(ext[:2]))

    print()
    if BAD:
        print(f'FAIL {len(BAD)}건 — ' + ' / '.join(BAD)); return 1
    print('PASS — 내장 설문 검증 전부 통과'); return 0

if __name__ == '__main__':
    sys.exit(main())

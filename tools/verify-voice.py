#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대사 음성 자동 검증 — W0~W9.

로컬 서버가 필요하다:  python3 -m http.server 8899  (저장소 루트에서)

  python3 tools/verify-voice.py                    # W0 이 build-voice.py check 를 먼저 돌린다
  python3 tools/verify-voice.py --allow-unvoiced   # 대사를 고쳐 일부 줄의 음성을 포기한 뒤

음성은 '실제 입력'(클릭·키)으로만 시작시킨다 — 자동재생 허용 플래그를 주지 않으므로,
제스처 없이 play() 가 통하는 환경이면 W1 이 먼저 실패한다(검증이 공허해지는 것을 막는다).
기대값은 전부 페이지에서 읽는다(VOICE.have · VOICE.key): 대사를 고쳐 일부 줄이 무음이
된 뒤에도 '파일 있는 줄은 재생, 없는 줄은 무음·무요청'을 그대로 검사한다.

이 스크립트는 '재생 동작'을 본다 — 파일의 내용이 그 대사가 맞는지는 W0(build-voice.py check 의
해시 대조)이 맡는다. 둘은 한 벌이다.

W0 정합성(build-voice.py check)   W1 자가검증(무제스처 재생 거부)
W2 전체 플레이 — 사건 2개 × 표준/빠른, 대화 화면의 모든 줄·심문 답변·엔딩 글이 제 파일로
재생되고 탑재된 음성 전부(VOICE.have)를 한 번 이상 들었는지
W3 정지 경로(다음 줄·대화 종료·답변 닫기 4종·인물 선택으로·로비 이탈 4종)
   — 검사에 쓸 줄은 페이지에서 고른다(음성 있는 답변, 음성 있는 줄이 둘·셋 이어지는 대화, 엔딩 글에 음성이
   있는 사건, 빠른 조사 첫 줄에 음성이 있는 사건). 그런 줄이 하나도 없어 못 한 검사는 '건너뜀'으로 적고,
   그때는 마지막 줄이 'PASS(부분)'이다(건너뜀은 통과가 아니다). 재생 중인 음성 요소의 수도 센다 — 겹치면 실패.
W4 같은 질문 다시 묻기   W5 음소거 연동·음량 불변   W6 고친 대사는 무음·무요청
W7 키보드만으로 완주   W8 키오스크 무입력 복귀   W9 위생(에러·4xx·외부 요청)
"""
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = 'http://localhost:8899/index.html'
OK, BAD, SKIP = [], [], []
for _s in (sys.stdout, sys.stderr):   # 한국어 윈도우 cp949 리다이렉트에서 '—' 로 죽지 않게
    try: _s.reconfigure(errors='replace')
    except AttributeError: pass


def chrome():
    for p in (os.environ.get('BIB_CHROME'), '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', '/opt/pw-browsers/chromium'):
        if p and os.path.exists(p): return p
    return None


def check(name, cond, extra=''):
    (OK if cond else BAD).append(name + (f' — {extra}' if extra and not cond else ''))
    print(('  OK  ' if cond else '  FAIL') + ' ' + name + ('' if cond else f'  ← {extra}'))


def section(t): print(f'[{t}]')


def skip(name, why):
    # 대사를 고쳐 음성을 포기한 뒤(--allow-unvoiced)에는 '그 줄이 재생된다'를 전제한 검사를 할 수 없다 —
    # 실패가 아니라 건너뜀으로 적는다(공허한 통과로 세지 않는다).
    SKIP.append(name); print(f'  --   {name}  (건너뜀 — {why})')
def active(pg): return pg.evaluate("document.querySelector('.screen.active').id")


# 검사는 VOICE.el 하나만 들여다보면 안 된다 — say() 가 줄마다 새 요소를 만들면 예전 음성이 계속 울려도
# VOICE.el 은 멀쩡해 보인다. play() 가 불린 모든 미디어 요소를 적어 두고, 음성 파일을 내고 있는 수(n)를 센다.
TRACK = """(()=>{ const set=new Set(); window.__media=set; const P=HTMLMediaElement.prototype, play=P.play;
  P.play=function(){ set.add(this); return play.apply(this, arguments); }; })()"""
ST = """(()=>{ const a=VOICE.el;
  return {scr:document.querySelector('.screen.active').id, cur:VOICE.cur,
    n:[...(window.__media||[])].filter(m=>!m.paused&&!m.ended&&/assets\\/voice\\//.test(m.currentSrc)).length,
    file:a&&a.currentSrc?a.currentSrc.split('/').pop().split('?')[0]:null,
    paused:a?a.paused:true, t:a?a.currentTime:0, muted:a?a.muted:null, vol:a?a.volume:null,
    err:a&&a.error?a.error.code:null}; })()"""
LINE = """(()=>{ const l=G.dlgQueue[G.dlgIdx], who=l.name.split(' · ')[0], k=VOICE.key(who,l.text);
  return {who, key:k, has:VOICE.have.has(k), typing:!!G._tw}; })()"""


def st(pg): return pg.evaluate(ST)


def wait_playing(pg, key, ms=2500):
    """key 의 파일이 실제로 굴러가는지(일시정지 아님 + 재생 위치 전진) 기다린다. 걸린 시간(ms) 또는 None."""
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        s = st(pg)
        if s['cur'] == key and s['file'] == key + '.mp3' and not s['paused'] and s['t'] > 0.03:
            return (time.time() - t0) * 1000
        pg.wait_for_timeout(20)
    return None


def silent(pg):
    s = st(pg)
    return s['cur'] is None and s['paused'] and s['n'] == 0


HEARD, LAT = set(), []
# 검사 대상 줄은 페이지에서 고른다 — 특정 대사를 코드에 박아 두면 그 줄을 고쳤을 때 거짓 실패가 난다.
PICK_ANSWER = """(()=>{ const cs=Object.keys(CASES);     // 음성이 있는 심문 답변 하나 (잠긴 질문이어도 된다 — ask 가 푼다)
  for(let ci=0;ci<cs.length;ci++){ const P=CASES[cs[ci]].PEOPLE, ps=Object.keys(P);
    for(let pi=0;pi<ps.length;pi++){ const p=P[ps[pi]];
      for(let qi=0;qi<p.qs.length;qi++){ const k=VOICE.key(p.name.split(' · ')[0], p.qs[qi].a);
        if(VOICE.have.has(k)) return {ci,pi,qi,key:k}; } } }
  return null; })()"""
PICK_END = """(()=>{ const cs=Object.keys(CASES);        // 엔딩 글에 음성이 있는 사건 (없으면 첫 사건)
  for(let ci=0;ci<cs.length;ci++) if(VOICE.have.has(VOICE.key('내레이션', CASES[cs[ci]].ending.text))) return {ci,has:true};
  return {ci:0,has:false}; })()"""
UNLOCK = "G.clues=new Set(Object.keys(G.C.CLUES)); Object.keys(G.C.TESTI).forEach(t=>G.testis.add(t)); G.renderHub()"
PICK_RUN = """(n=>{ const cs=Object.keys(CASES);      // 음성 있는 줄이 n개 이어지는 대화 (프롤로그·진상, 표준·빠른 조사)
  for(const arr of ['PROLOGUE','fastPrologue','REVEAL','fastReveal'])
    for(let ci=0;ci<cs.length;ci++){ const L=CASES[cs[ci]][arr]; if(!L) continue;
      const K=L.map(l=>VOICE.key(l.name.split(' · ')[0], l.text));
      for(let i=0;i+n<=L.length;i++) if(K.slice(i,i+n).every(k=>VOICE.have.has(k)))
        return {ci, ck:cs[ci], arr, fast:arr.startsWith('fast'), i, k:K}; }
  return null; })"""
PICK_FAST0 = """(()=>{ const cs=Object.keys(CASES);      // 빠른 조사 프롤로그의 첫 줄에 음성이 있는 사건
  for(let ci=0;ci<cs.length;ci++){ const l=(CASES[cs[ci]].fastPrologue||CASES[cs[ci]].PROLOGUE)[0];
    if(VOICE.have.has(VOICE.key(l.name.split(' · ')[0], l.text))) return ci; }
  return null; })()"""


def open_run(pg, run, edit=None):
    """고른 대화의 i번째 줄까지 간다. 진상(REVEAL)은 프롤로그를 넘긴 뒤 그 대화를 직접 연다 — 음성은 사건을
    시작한 클릭으로 이미 풀려 있고, 줄을 넘기는 것은 전부 실제 Enter 다."""
    pg.goto(f"{BASE}?fast={int(run['fast'])}"); pg.wait_for_timeout(400)
    if edit is not None: pg.evaluate(f"CASES.{run['ck']}.{run['arr']}[{edit}].text += ' 부탁드립니다.'")
    pg.click('#scr-title .btn'); pg.click(f"#caseGrid .case-card >> nth={run['ci']}"); settle(pg)
    if 'eveal' in run['arr']:
        dialog(pg, 'run', [])
        pg.evaluate(f"G.playDialog(G.C.{run['arr']}, ()=>G.show('scr-hub'))")
    for _ in range(run['i']): next_line(pg)


def next_line(pg):
    if pg.evaluate('!!G._tw'): pg.keyboard.press('Enter'); pg.wait_for_timeout(30)
    pg.keyboard.press('Enter'); pg.wait_for_timeout(40)


def ask(pg, ans, menu_open=False):
    if not menu_open:
        pg.evaluate(UNLOCK)        # 고른 질문이 단서·증언을 요구할 수 있다 — 상태를 채워 잠금을 푼다(허브에서만)
        pg.click('#talkMenuBtn')
    pg.click(f"#hubGrid .room-card >> nth={ans['pi']}"); pg.click(f"#talkQs .q-btn >> nth={ans['qi']}")


def dialog(pg, tag, problems, first_enter=True):
    """대화 화면을 끝까지 넘기며 줄마다 음성을 검사한다. 진행은 키보드(Enter)만 쓴다."""
    for _ in range(40):
        if active(pg) != 'scr-dialog': return
        ln = pg.evaluate(LINE)
        if ln['has']:
            ms = wait_playing(pg, ln['key'])
            if ms is None: problems.append(f"{tag} {ln['who']} {ln['key']} 재생 안 됨 {st(pg)}")
            else:
                HEARD.add(ln['key']); LAT.append(ms)
                if st(pg)['n'] != 1: problems.append(f"{tag} {ln['key']} 음성이 겹친다 {st(pg)}")
                if first_enter and pg.evaluate('!!G._tw'):
                    # 첫 Enter 는 글자만 마저 채운다 — 음성은 끊기지도, 처음으로 되감기지도 않아야 한다
                    t1 = st(pg)['t']; pg.keyboard.press('Enter'); pg.wait_for_timeout(120); s = st(pg)
                    if not (s['scr'] == 'scr-dialog' and s['cur'] == ln['key'] and not s['paused'] and s['t'] > t1):
                        problems.append(f"{tag} {ln['key']} 첫 Enter 가 음성을 건드림 {s}")
        else:
            pg.wait_for_timeout(60)
            if not silent(pg): problems.append(f"{tag} {ln['who']} 파일 없는 줄인데 소리가 남 {st(pg)}")
        if pg.evaluate('!!G._tw'): pg.keyboard.press('Enter'); pg.wait_for_timeout(30)
        pg.keyboard.press('Enter'); pg.wait_for_timeout(40)
    problems.append(f'{tag} 대화가 끝나지 않음')


def settle(pg):
    """카드를 마우스로 누른 직후 한두 프레임은 포커스가 (이미 숨은) 카드에 남아 있을 수 있다. 그 순간의
    Enter 는 게임의 '포커스된 카드 활성화' 경로를 타서 사건을 다시 시작한다(사람 손으로는 불가능한 간격,
    30회 중 14회 재현) — 키를 보내기 전에 포커스가 카드를 떠나기를 기다린다."""
    pg.wait_for_function("!document.activeElement.classList.contains('case-card')"
                         " && !document.activeElement.classList.contains('room-card')", timeout=2000)


def start(pg, idx, fast, url=None):
    pg.goto(f'{url or BASE}?fast={int(fast)}'); pg.wait_for_timeout(400)
    pg.click('#scr-title .btn'); pg.click(f'#caseGrid .case-card >> nth={idx}'); settle(pg)


def clues(pg, tag, problems):
    for ri, rk in enumerate(pg.evaluate('Object.keys(G.C.ROOMS)')):
        pg.click(f'#hubGrid .room-card >> nth={ri}')
        spots = pg.evaluate(f"G.C.ROOMS['{rk}'].spots.map(s=>s.clue?'c':'')")
        for si in [i for i, s in enumerate(spots) if s == 'c']:
            pg.click(f'#spots .spot-btn >> nth={si}'); dialog(pg, tag + ' 단서', problems, first_enter=False)
        pg.click('#roomBack')


CLOSERS = ['Escape', 'Enter', 'Space', 'click']


def talks(pg, tag, problems, closes):
    n = 0
    for _ in range(2):   # 증언으로 열리는 질문까지
        for pi, pk in enumerate(pg.evaluate('Object.keys(G.C.PEOPLE)')):
            pg.click('#talkMenuBtn'); pg.click(f'#hubGrid .room-card >> nth={pi}')
            for qi in range(pg.evaluate(f"G.C.PEOPLE['{pk}'].qs.length")):
                b = pg.evaluate(f"(()=>{{const b=document.querySelectorAll('#talkQs .q-btn')[{qi}]; return [b.classList.contains('locked'), b.classList.contains('asked')]}})()")
                if b[0] or b[1]: continue
                pg.click(f'#talkQs .q-btn >> nth={qi}')
                k = pg.evaluate(f"(()=>{{const p=G.C.PEOPLE['{pk}']; return VOICE.key(p.name.split(' · ')[0], p.qs[{qi}].a)}})()")
                if pg.evaluate(f"VOICE.have.has('{k}')"):
                    ms = wait_playing(pg, k)
                    if ms is None: problems.append(f'{tag} 답변 {pk}#{qi} {k} 재생 안 됨 {st(pg)}')
                    else:
                        HEARD.add(k); LAT.append(ms)
                        if st(pg)['n'] != 1: problems.append(f'{tag} 답변 {pk}#{qi} 음성이 겹친다 {st(pg)}')
                elif not silent(pg): problems.append(f'{tag} 답변 {pk}#{qi} 파일 없는데 소리가 남')
                how = CLOSERS[n % 4]; n += 1
                if how == 'click': pg.click('#talkAnswer')
                else: pg.keyboard.press(how)
                pg.wait_for_timeout(40)
                shut = pg.evaluate("G.$('talkAnswer').style.display") == 'none' and silent(pg)
                closes.setdefault(how, []).append(shut)
            pg.click('#talkBack'); pg.click('#talkMenuBtn')


def deduce(pg, tag, problems, regroup):
    pg.click('#deduceBtn'); dialog(pg, tag + ' 추리 도입', problems)
    if regroup:   # 촛불 3개를 모두 꺼 재정비 대사를 부른다
        ans = pg.evaluate('G.DQ[0].ans')
        for w in [i for i in range(4) if i != ans][:3]:
            pg.keyboard.press(str(w + 1)); pg.wait_for_timeout(120)
        if active(pg) != 'scr-dialog': problems.append(f'{tag} 재정비 대사가 뜨지 않음')
        dialog(pg, tag + ' 재정비', problems)
    for _ in range(pg.evaluate('G.DQ.length')):
        pg.keyboard.press(str(pg.evaluate('G.DQ[G.deduceIdx].ans') + 1)); pg.wait_for_timeout(1750)


def sim_then_reveal(pg, tag, problems):
    for i, ok in enumerate(pg.evaluate('G.C.SIM.actions.map(a=>!!a.ok)')):
        if ok: pg.keyboard.press(str(i + 1)); pg.wait_for_timeout(80)
    # 여기서부터 입력을 넣지 않는다 — 진상 공개 첫 줄은 타이머(배너 뒤)가 여는 대사다
    for _ in range(80):
        if active(pg) == 'scr-dialog': break
        pg.wait_for_timeout(50)
    ln = pg.evaluate(LINE)
    timer_ok = (wait_playing(pg, ln['key']) is not None) if ln['has'] else silent(pg)
    dialog(pg, tag + ' 진상', problems)
    return timer_ok


def play(pg, idx, fast, url=None):
    start(pg, idx, fast, url)
    tag = f'{pg.evaluate("G.caseKey")}/{"빠른" if fast else "표준"}'
    problems, closes = [], {}
    dialog(pg, tag + ' 프롤로그', problems)
    clues(pg, tag, problems)
    talks(pg, tag, problems, closes)
    deduce(pg, tag, problems, regroup=not fast)
    timer_ok = sim_then_reveal(pg, tag, problems)
    check(f'{tag} 모든 대사가 제 파일로 재생(파일 없는 줄은 무음)', not problems, problems[:3])
    check(f'{tag} 타이머가 연 진상 공개 첫 줄도 입력 없이 재생', timer_ok)
    check(f'{tag} 엔딩 도달 · 엔딩 글 낭독(파일 없으면 무음)', active(pg) == 'scr-end' and ending_voice(pg), st(pg))
    return closes


def ending_voice(pg):
    k = pg.evaluate("VOICE.key('내레이션', G.C.ending.text)")
    if not pg.evaluate(f"VOICE.have.has('{k}')"): return silent(pg)
    ms = wait_playing(pg, k)
    if ms is None: return False
    HEARD.add(k); LAT.append(ms)
    return True


def main():
    try:
        urllib.request.urlopen(BASE, timeout=3)
    except Exception:
        print('로컬 서버가 없다 — 저장소 루트에서: python3 -m http.server 8899'); return 2
    section('W0 정합성')
    # 8899 에 다른 폴더의 서버가 떠 있으면 이 저장소가 아니라 그쪽을 검사하게 된다 — 먼저 확인한다.
    same = urllib.request.urlopen(BASE, timeout=5).read() == (ROOT / 'index.html').read_bytes()
    check('localhost:8899 가 이 폴더의 index.html 을 서비스한다', same)
    if not same:
        print('8899 의 서버가 다른 폴더를 서비스하고 있다 — 이 저장소 루트에서 다시 띄운다'); return 2
    extra = [x for x in sys.argv[1:] if x == '--allow-unvoiced']
    r = subprocess.run([sys.executable, str(ROOT / 'tools/build-voice.py'), 'check', *extra], capture_output=True, text=True)
    check('build-voice.py check — 대사 ↔ 목록 ↔ 파일 ↔ 대본 ↔ 원본(해시)', r.returncode == 0,
          ' / '.join((r.stdout + r.stderr).strip().splitlines()[-4:]))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=chrome(), headless=True)   # 자동재생 허용 플래그 없음
        section('W1 자가검증')
        ctx0 = b.new_context()   # 이 컨텍스트에서만: 로드 직후 제스처 없이 play() 를 걸어 본다
        ctx0.add_init_script("""window.addEventListener('DOMContentLoaded',()=>{ const k=(VOICE_HAVE.split(' ')[0]||'');
          if(!k){ window.__noGesture='no-voice'; return; }
          const a=new Audio('assets/voice/'+k+'.mp3'); const p=a.play();
          p.then(()=>{ window.__noGesture='played'; a.pause(); }, e=>{ window.__noGesture=e.name; }); });""")
        pg0 = ctx0.new_page(); pg0.goto(BASE + '?fast=0'); pg0.wait_for_timeout(700)
        check('제스처 없는 play() 는 거부된다 — 이 브라우저는 자동재생을 막는다',
              pg0.evaluate('window.__noGesture') == 'NotAllowedError', pg0.evaluate('window.__noGesture'))
        ctx0.close()

        ctx = b.new_context(viewport={'width': 1280, 'height': 800})
        ctx.add_init_script(TRACK)
        pg = ctx.new_page()
        errs, ext, bad_status, failed, voice_reqs = [], [], [], [], []
        pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('request', lambda r: (voice_reqs.append(r.url) if '/assets/voice/' in r.url else None,
                                    ext.append(r.url) if not r.url.startswith(('http://localhost:8899', 'data:', 'blob:')) else None))
        pg.on('response', lambda r: bad_status.append(f'{r.status} {r.url[-40:]}') if r.status >= 400 else None)
        # 줄을 넘기면 받던 음성 다운로드가 중단된다(ERR_ABORTED) — 그것만 정상으로 본다
        pg.on('requestfailed', lambda r: failed.append(f'{r.url[-40:]} {r.failure}')
              if not ('ERR_ABORTED' in str(r.failure) and ('/assets/voice/' in r.url or '/assets/bgm/' in r.url)) else None)

        pg.goto(BASE + '?fast=0'); pg.wait_for_timeout(700)
        n_have = pg.evaluate('VOICE.have.size')
        check(f'음성 파일 목록 {n_have}개 탑재', n_have > 0)
        check('타이틀에서는 음성 요소도 요청도 없다', pg.evaluate('VOICE.el===null') and not voice_reqs, voice_reqs[:3])

        section('W2 전체 플레이')
        closes = {}
        for idx in (0, 1):
            for fast in (False, True):
                for how, v in play(pg, idx, fast).items(): closes.setdefault(how, []).extend(v)
        have = set(pg.evaluate('[...VOICE.have]'))
        check(f'들은 음성 {len(HEARD)}개 = 탑재된 음성 {len(have)}개 전부', HEARD == have, sorted(have - HEARD)[:5])
        lat = sorted(LAT)
        print(f'       재생 시작까지: 중앙값 {lat[len(lat) // 2]:.0f}ms · 최대 {lat[-1]:.0f}ms (localhost, {len(lat)}회)')

        section('W3 정지 경로')
        for how in CLOSERS:
            v = closes.get(how, [])
            check(f'답변 닫기 — {how} ({len(v)}회) 패널 닫힘·음성 정지', bool(v) and all(v))
        duo = pg.evaluate(PICK_RUN + '(2)'); tri = pg.evaluate(PICK_RUN + '(3)'); ans = pg.evaluate(PICK_ANSWER)
        if duo:
            open_run(pg, duo)
            k0, k1 = duo['k'][duo['i']], duo['k'][duo['i'] + 1]
            ok0 = wait_playing(pg, k0) is not None
            next_line(pg)
            ok1 = k1 != k0 and wait_playing(pg, k1) is not None
            check('다음 줄로 넘기면 음성도 다음 줄로 바뀐다 — 한 번에 한 음성만', ok0 and ok1 and st(pg)['n'] == 1, st(pg))
        else:
            skip('다음 줄로 넘기면 음성도 다음 줄로 바뀐다 — 한 번에 한 음성만', '음성 있는 줄이 둘 이어지는 대화가 없다')
        start(pg, 0, False)
        for _ in range(12):
            if active(pg) != 'scr-dialog': break
            pg.keyboard.press('Enter'); pg.wait_for_timeout(40)
        check('대화가 끝나 허브로 — 음성 정지', active(pg) == 'scr-hub' and silent(pg), st(pg))
        if ans:
            ka = ans['key']
            start(pg, ans['ci'], False); dialog(pg, 'W3', [])
            ask(pg, ans); playing = wait_playing(pg, ka) is not None
            pg.click('#talkBack'); pg.wait_for_timeout(60)
            check('[인물 선택으로] — 답변 음성 정지', playing and silent(pg) and active(pg) == 'scr-hub', st(pg))
            ask(pg, ans, menu_open=True); playing = wait_playing(pg, ka) is not None
            pg.evaluate('G.backToLobby()'); pg.wait_for_timeout(60)   # 심문 화면엔 로비 버튼이 없다 — 관문 함수 직접 호출
            check('backToLobby — 답변 패널 닫힘·음성 정지', playing and active(pg) == 'scr-lobby' and silent(pg)
                  and pg.evaluate("G.$('talkAnswer').style.display") == 'none', st(pg))
        else:
            for nm in ('[인물 선택으로] — 답변 음성 정지', 'backToLobby — 답변 패널 닫힘·음성 정지'):
                skip(nm, '음성 있는 심문 답변이 하나도 없다')
        # 허브의 [로비로] (실제 클릭)
        start(pg, 0, True); dialog(pg, 'W3', [])
        pg.click('#scr-hub .btn.back'); pg.wait_for_timeout(80)
        check('허브 [로비로] — 로비·음성 정지', active(pg) == 'scr-lobby' and silent(pg), st(pg))
        # 추리 2press — 마지막 정답 직후 1.6초 연출 중에 이탈
        ready = "G.clues=new Set(Object.keys(G.C.CLUES)); G.testis.add(G.C.needTesti); G.renderHub()"
        start(pg, 0, True); dialog(pg, 'W3', []); pg.evaluate(ready)
        pg.click('#deduceBtn'); dialog(pg, 'W3', [])
        n = pg.evaluate('G.DQ.length')
        for i in range(n):
            pg.keyboard.press(str(pg.evaluate('G.DQ[G.deduceIdx].ans') + 1))
            if i < n - 1: pg.wait_for_timeout(1750)
        pg.click('#dedLobbyBtn'); pg.click('#dedLobbyBtn'); pg.wait_for_timeout(3000)
        check('추리 2press 이탈 — 3초 뒤에도 로비·무음(연출 타이머가 대사를 열지 않는다)',
              active(pg) == 'scr-lobby' and silent(pg), st(pg))
        # 재현 2press — 성공 배너 타이머가 진상 공개(음성)를 열기 직전에 이탈
        start(pg, 0, True); dialog(pg, 'W3', []); pg.evaluate(ready)
        pg.click('#deduceBtn'); dialog(pg, 'W3', [])
        for _ in range(n):
            pg.keyboard.press(str(pg.evaluate('G.DQ[G.deduceIdx].ans') + 1)); pg.wait_for_timeout(1750)
        for i, ok in enumerate(pg.evaluate('G.C.SIM.actions.map(a=>!!a.ok)')):
            if ok: pg.keyboard.press(str(i + 1)); pg.wait_for_timeout(60)
        pg.click('#simLobbyBtn'); pg.click('#simLobbyBtn'); pg.wait_for_timeout(3200)
        check('재현 2press 이탈 — 3초 뒤에도 로비·무음·누출음 꺼짐',
              active(pg) == 'scr-lobby' and silent(pg) and pg.evaluate('SND.wantHiss') is False, st(pg))
        # 엔딩 글이 낭독되는 중에 [수사관 임명장] / [다른 사건 파일] — 엔딩 글에 음성이 있는 사건에서 본다
        end = pg.evaluate(PICK_END)
        start(pg, end['ci'], True); dialog(pg, 'W3', []); pg.evaluate(ready)
        pg.click('#deduceBtn'); dialog(pg, 'W3', [])
        for _ in range(pg.evaluate('G.DQ.length')):
            pg.keyboard.press(str(pg.evaluate('G.DQ[G.deduceIdx].ans') + 1)); pg.wait_for_timeout(1750)
        sim_then_reveal(pg, 'W3', [])
        told = ending_voice(pg)
        pg.click('#certBtn', no_wait_after=True); pg.wait_for_timeout(300); kept = st(pg)
        pg.click('#scr-end .btn >> nth=1'); pg.wait_for_timeout(80)
        left = active(pg) == 'scr-lobby' and silent(pg)
        if end['has']:
            check('엔딩 글 낭독 중 [수사관 임명장]은 음성을 끊지 않고, [다른 사건 파일]은 끊는다',
                  told and not kept['paused'] and left, (told, kept, st(pg)))
        else:
            skip('엔딩 글 낭독 중 [수사관 임명장]은 음성을 끊지 않는다', '엔딩 글에 음성이 있는 사건이 없다')
            check('엔딩(음성 없음) → [다른 사건 파일] — 로비·무음', told and left, st(pg))

        section('W4 같은 질문 다시 묻기')
        if ans:
            start(pg, ans['ci'], False); dialog(pg, 'W4', [])
            ask(pg, ans); first = wait_playing(pg, ka) is not None
            pg.wait_for_timeout(900); t_far = st(pg)['t']
            pg.keyboard.press('Escape'); pg.wait_for_timeout(50)
            pg.click(f"#talkQs .q-btn >> nth={ans['qi']}"); again = wait_playing(pg, ka) is not None; t_again = st(pg)['t']
            check('닫았다가 다시 물으면 처음부터 다시 재생', first and again and t_again < t_far, (t_far, t_again))
            pg.click(f"#talkQs .q-btn >> nth={ans['qi']}"); pg.wait_for_timeout(250); s_ = st(pg)
            check('답변이 떠 있는 채로 다시 눌러도 처음부터 재생', s_['cur'] == ka and not s_['paused'] and s_['t'] < 0.6, s_)

            section('W5 음소거 연동')
            m0 = st(pg)['muted']
            pg.keyboard.press('Escape'); pg.click('#talkBack'); pg.click('#talkMenuBtn')
            pg.click('#sndBtn'); m_off_idle = st(pg)['muted']
            ask(pg, ans); wait_playing(pg, ka); m_off = st(pg)['muted']
            pg.keyboard.press('Escape'); pg.click('#talkBack'); pg.click('#talkMenuBtn')
            pg.click('#sndBtn')
            ask(pg, ans); on_air = wait_playing(pg, ka) is not None; s_ = st(pg); m_on = s_['muted']
            check('사운드 끄면 음성도 muted, 다시 켜면 풀린다', [m0, m_off_idle, m_off, m_on] == [False, True, True, False],
                  [m0, m_off_idle, m_off, m_on])
            check('음량은 파일에 구워져 있다 — 재생 중 volume 은 1 그대로', on_air and not s_['paused'] and s_['vol'] == 1, s_)
        else:
            for nm in ('닫았다가 다시 물으면 처음부터 다시 재생', '답변이 떠 있는 채로 다시 눌러도 처음부터 재생',
                       '사운드 끄면 음성도 muted, 다시 켜면 풀린다', '음량은 파일에 구워져 있다 — 재생 중 volume 은 1 그대로'):
                skip(nm, '음성 있는 심문 답변이 하나도 없다')

        section('W6 고친 대사')
        if tri:
            i = tri['i']
            open_run(pg, tri, edit=i + 1)          # 가운데 줄만 고친다
            ok0 = wait_playing(pg, tri['k'][i]) is not None
            if pg.evaluate('!!G._tw'): pg.keyboard.press('Enter'); pg.wait_for_timeout(40)
            before = len(voice_reqs); e0 = len(errs)
            pg.keyboard.press('Enter'); pg.wait_for_timeout(500)
            ln = pg.evaluate(LINE)
            check('고친 줄은 무음 — 직전 음성도 끊긴다', ok0 and not ln['has'] and silent(pg), (ln, st(pg)))
            check('고친 줄은 파일 요청도 에러도 없다', len(voice_reqs) == before and len(errs) == e0, voice_reqs[before:])
            next_line(pg)
            check('그다음 줄은 다시 정상 재생', wait_playing(pg, tri['k'][i + 2]) is not None, st(pg))
        else:
            for nm in ('고친 줄은 무음 — 직전 음성도 끊긴다', '고친 줄은 파일 요청도 에러도 없다', '그다음 줄은 다시 정상 재생'):
                skip(nm, '음성 있는 줄이 셋 이어지는 대화가 없다')

        section('W7 키보드만으로 완주')
        def kb(sel, n=0, key='Enter'):
            js = f"document.activeElement===document.querySelectorAll({json.dumps(sel)})[{n}]"
            for _ in range(80):
                if pg.evaluate(js): pg.keyboard.press(key); pg.wait_for_timeout(60); return True
                pg.keyboard.press('Tab')
            return False
        heard_kb, prob = len(HEARD), []
        pg.goto(BASE + '?fast=1'); pg.wait_for_timeout(400)
        kb('#scr-title .btn'); kb('#caseGrid .case-card', 0); settle(pg)
        dialog(pg, 'W7 프롤로그', prob)
        for ri, rk in enumerate(pg.evaluate('Object.keys(G.C.ROOMS)')):
            kb('#hubGrid .room-card', ri)
            for si in pg.evaluate(f"G.C.ROOMS['{rk}'].spots.map((s,i)=>s.clue?i:-1).filter(i=>i>=0)"):
                kb('#spots .spot-btn', si); dialog(pg, 'W7 단서', prob, first_enter=False)
            kb('#roomBack')
        for _ in range(2):
            for pi, pk in enumerate(pg.evaluate('Object.keys(G.C.PEOPLE)')):
                kb('#talkMenuBtn'); kb('#hubGrid .room-card', pi)
                for qi in range(pg.evaluate(f"G.C.PEOPLE['{pk}'].qs.length")):
                    if pg.evaluate(f"document.querySelectorAll('#talkQs .q-btn')[{qi}].className.match(/locked|asked/)!==null"): continue
                    kb('#talkQs .q-btn', qi)
                    k = pg.evaluate(f"(()=>{{const p=G.C.PEOPLE['{pk}']; return VOICE.key(p.name.split(' · ')[0], p.qs[{qi}].a)}})()")
                    if pg.evaluate(f"VOICE.have.has('{k}')") and wait_playing(pg, k) is None: prob.append(f'W7 답변 {pk}#{qi}')
                    pg.keyboard.press('Enter'); pg.wait_for_timeout(50)
                    if not silent(pg): prob.append(f'W7 답변 닫기 {pk}#{qi}')
                kb('#talkBack'); kb('#talkMenuBtn')
        kb('#deduceBtn'); dialog(pg, 'W7 추리 도입', prob)
        for _ in range(pg.evaluate('G.DQ.length')):
            pg.keyboard.press(str(pg.evaluate('G.DQ[G.deduceIdx].ans') + 1)); pg.wait_for_timeout(1750)
        sim_then_reveal(pg, 'W7', prob)
        check('마우스 없이 엔딩까지 — 음성 재생·정지 정상', active(pg) == 'scr-end' and not prob, (active(pg), prob[:3]))

        section('W8 키오스크 무입력 복귀')
        kc = pg.evaluate(PICK_FAST0)
        start(pg, kc if kc is not None else 0, True)
        pg.evaluate('G.KIOSK_WARN=1500; G.KIOSK_OUT=3000')
        k0 = pg.evaluate(LINE)['key']
        was = wait_playing(pg, k0) is not None if kc is not None else None
        pg.wait_for_timeout(1600); still = st(pg)
        pg.wait_for_timeout(3600)
        back = active(pg) == 'scr-title' and pg.evaluate('VOICE.el===null')
        if kc is not None:
            check('음성이 나오는 중에도 무입력이면 처음 화면으로 돌아간다(음성은 입력이 아니다)',
                  was and still['cur'] == k0 and back, (still, active(pg)))
        else:
            skip('음성이 나오는 중에도 무입력이면 처음 화면으로 돌아간다(음성은 입력이 아니다)', '빠른 조사 첫 줄에 음성이 있는 사건이 없다')
            check('무입력이면 처음 화면으로 돌아간다(음성 없는 줄에서)', back, active(pg))

        section('W9 위생')
        check('콘솔·페이지 에러 0건', not errs, errs[:5])
        check('외부 네트워크 요청 0건', not ext, ext[:5])
        check('4xx/5xx 응답 0건', not bad_status, bad_status[:5])
        check('실패 요청 0건(줄 넘김에 따른 다운로드 중단 제외)', not failed, failed[:5])
        used = {u.split('/')[-1].split('?')[0][:-4] for u in voice_reqs}
        check(f'요청된 음성 파일 {len(used)}종 — 전부 목록(VOICE_HAVE) 안', used <= have, sorted(used - have)[:5])
        b.close()

    print(f'\n통과 {len(OK)} / 실패 {len(BAD)}' + (f' / 건너뜀 {len(SKIP)}' if SKIP else ''))
    if BAD:
        for x in BAD: print('  FAIL ' + x)
        return 1
    if SKIP:
        # 건너뛴 검사는 '통과'가 아니다 — 그 동작은 이번 실행에서 확인되지 않았다.
        for x in SKIP: print('  --   ' + x)
        print(f'PASS(부분) — 실패는 없지만 위 {len(SKIP)}건은 음성 없는 줄 때문에 검사하지 못했다(건너뜀은 통과가 아니다)')
        return 0
    print('PASS — 대사 음성 검증 전부 통과')
    return 0


if __name__ == '__main__':
    sys.exit(main())

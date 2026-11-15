#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대사 음성 자동 검증 — W0~W10.

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
재생되고 탑재된 음성 전부(VOICE.have)를 한 번 이상 들었는지. 줄마다 시작 순간의 음소거·음량·속도가
기본값인지, 재생이 확인되기까지 걸린 시간의 묶음별(대화·단서·답변) 중앙값이 500ms 안인지(표본 8개 미만인
묶음은 판단하지 않는다 · 일부 줄만 늦는 것은 지나친다), 타자 효과 도중의 첫 Enter 가 음성을 건드리지 않는지
(대화 줄·단서 설명 줄 — Enter 가 도착했을 때 타자 효과가 돌던 줄에서만), 음성이 나던 중에 대화를 닫으면
넘어간 화면(허브·방·추리)에서 끊겨 있는지도 여기서 본다.
W3 정지 경로(다음 줄·답변 닫기 4종·인물 선택으로·로비/엔딩 이탈 5종)
   — 검사에 쓸 줄은 페이지에서 고른다(음성 있는 답변, 음성 있는 줄이 둘·셋 이어지는 대화, 엔딩 글에 음성이
   있는 사건, 빠른 조사 첫 줄에 음성이 있는 사건). 그런 줄이 하나도 없어 못 한 검사는 '건너뜀'으로 적고,
   그때는 마지막 줄이 'PASS(부분)'이다(건너뜀은 통과가 아니다). 재생 중인 음성 요소의 수도 센다 — 겹치면 실패.
W4 같은 질문 다시 묻기   W5 음소거 연동(첫 음성 전에 끈 경우 포함)·음량 불변   W6 고친 대사는 무음·무요청
W7 키보드만으로 완주
W8 키오스크 무입력 복귀 — 음성이 나는 도중에도(짧은 한도), 끝난 뒤에도(음성보다 긴 한도) 돌아가는지,
   그리고 음성이 시작·종료돼도 무입력 시계(G._kioskLast)가 마지막 실제 입력 시각 그대로인지
W9 끝까지 듣기 — 다섯 줄(대화의 첫 줄·그다음 줄, 단서 설명, 심문 답변, 엔딩 글)을 아무 입력 없이 끝까지
   둔다. 보는 것: 앞부분을 건너뛰지 않는다(재생 위치가 마지막 입력 뒤 흐른 시간보다 0.25초 넘게 앞서지
   않는다 — 늦게 시작한 만큼 건너뛴 것은 구별하지 못한다), 끝까지 실시간으로 간다(되감김·끊김·다시 로드 없음),
   그동안 음소거·음량·속도가 기본값 그대로다, 끝난 뒤 2.5초 동안 화면이 저절로 바뀌거나 다시 재생되지 않는다,
   (빠른 조사 링크에서는) 무입력 시계가 그대로다. 듣는 동안 페이지가 다시 로드되면 실패로 적는다. W2~W7 은 줄마다 0.1초쯤 듣고 넘기므로 '재생 도중'은
   여기서만 본다 — 탑재된 줄 가운데 다섯 줄뿐이다. 나머지 줄에서만 벌어지는 일은 보지 못한다.
W10 위생(에러·4xx·외부 요청)
종료 코드: 0 전부 통과 · 1 실패 있음 · 2 실행 불가(서버 없음·다른 폴더·playwright 없음) · 3 실패는 없지만 건너뛴 검사 있음.
검사 도중 예외로 끝나면(traceback) 요약 줄이 없고 종료 코드는 1이다 — 그것도 실패로 읽는다.
한계: 여기서 보는 것은 헤드리스 크로미움에서의 동작이다. 고친 줄이 많을수록 같은 동작을 확인하는 횟수가
줄어든다 — 검사 이름의 '(N회)'는 음성이 실제로 나던 경우만 센 횟수다. 전부 통과가 '음성 동작 전부 확인'은
아니다: 스피커로 소리가 나는지는 볼 수 없고(요소의 상태만 본다), 재생 도중의 동작은 W9 의 다섯 줄로만 본다.
python3 -m http.server 는 Range 요청을 받지 않아 음성 파일의 탐색(seek)이 되지 않는다 — 탐색으로 앞부분을
건너뛰는 종류의 결함은 이 서버에서는 드러나지 않는다(Range 를 받는 서버에서는 W9 의 '재생 위치가 입력 뒤 흐른
시간을 0.25초 넘게 앞서지 않음' 기준이 본다).
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
# 음성 파일에 대한 play() 호출 수(__plays)와 마지막 '실제 입력' 시각(__lastInput — 게임의 무입력 시계가 듣는
# 것과 같은 네 이벤트)도 적는다. 이 스크립트는 페이지 스크립트보다 먼저 실행되므로 리스너도 먼저 불린다.
TRACK = """(()=>{ const set=new Set(); window.__media=set; window.__plays=0; window.__lastInput=0;
  const P=HTMLMediaElement.prototype, play=P.play;
  P.play=function(){ set.add(this); if(/assets\\/voice\\//.test(this.src||'')) window.__plays++; return play.apply(this, arguments); };
  for(const ev of ['pointerdown','keydown','touchstart','wheel'])
    addEventListener(ev, ()=>{ window.__lastInput=Date.now(); }, {capture:true, passive:true});
  // 키가 '도착한 순간' 타자 효과가 돌고 있었는가 — 검사가 상태를 읽고 키를 보내는 사이에 타자 효과가 저절로 끝날 수 있다
  addEventListener('keydown', ()=>{ window.__twAtKey=(typeof G!=='undefined' && !!G._tw); }, {capture:true, passive:true}); })()"""
ST = """(()=>{ const a=VOICE.el;
  return {scr:document.querySelector('.screen.active').id, cur:VOICE.cur,
    n:[...(window.__media||[])].filter(m=>!m.paused&&!m.ended&&/assets\\/voice\\//.test(m.currentSrc)).length,
    file:a&&a.currentSrc?a.currentSrc.split('/').pop().split('?')[0]:null,
    paused:a?a.paused:true, ended:a?a.ended:false, t:a?a.currentTime:0, muted:a?a.muted:null, vol:a?a.volume:null, rate:a?a.playbackRate:null,
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


def plain(s):
    """사운드가 켜진 상태의 기본값인가 — 음소거 아님 · 음량 1 · 속도 1."""
    return s['muted'] is False and s['vol'] == 1 and s['rate'] == 1


HEARD = set()
LAT = {'대화': [], '단서': [], '답변': []}   # 재생이 확인되기까지 걸린 시간(ms), 줄의 종류별
FE = []          # 타자 효과 도중에 도착한 첫 Enter 가 음성을 그대로 뒀는가(줄마다)
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
PICK_FAST0 = """(()=>{ const cs=Object.keys(CASES), out=[];      // 빠른 조사 프롤로그의 첫 줄에 음성이 있는 사건들
  for(let ci=0;ci<cs.length;ci++){ const l=(CASES[cs[ci]].fastPrologue||CASES[cs[ci]].PROLOGUE)[0];
    if(VOICE.have.has(VOICE.key(l.name.split(' · ')[0], l.text))) out.push(ci); }
  return out; })()"""
PICK_FIRSTS = """(()=>{ const cs=Object.keys(CASES), out=[];     // 프롤로그 첫 줄(표준·빠른 조사) 가운데 음성이 있는 것 전부
  for(let ci=0;ci<cs.length;ci++) for(const fast of [false,true]){ const C=CASES[cs[ci]];
    if(fast&&!C.fastPrologue) continue;
    const l=(fast?C.fastPrologue:C.PROLOGUE)[0], k=VOICE.key(l.name.split(' · ')[0], l.text);
    if(VOICE.have.has(k)) out.push({ci,fast,key:k}); }
  return out; })()"""
PICK_ANSWERS = """(()=>{ const cs=Object.keys(CASES), out=[];    // 음성이 있는 심문 답변 전부
  for(let ci=0;ci<cs.length;ci++){ const P=CASES[cs[ci]].PEOPLE, ps=Object.keys(P);
    for(let pi=0;pi<ps.length;pi++){ const p=P[ps[pi]];
      for(let qi=0;qi<p.qs.length;qi++){ const k=VOICE.key(p.name.split(' · ')[0], p.qs[qi].a);
        if(VOICE.have.has(k)) out.push({ci,pi,qi,key:k}); } } }
  return out; })()"""
# 끝까지 들을 줄은 긴 것으로 고른다(도중에 벌어지는 일을 볼 시간이 길수록 좋다). 길이는 고르는 데만 쓰고,
# 검사의 기대값은 재생 중인 요소에서 읽는다 — 기록이 없으면 첫 후보를 쓴다.
try: DUR = {k: v.get('dur') or 0 for k, v in json.loads((ROOT / 'tools/voice/takes.json').read_text('utf-8')).items()}
except Exception: DUR = {}
LISTEN = """(()=>{ const a=VOICE.el, L=window.__lt={ended:0,early:0,seeking:0,play:0,emptied:0,ratechange:0,volumechange:0,plays0:window.__plays};
  a.addEventListener('ended',()=>L.ended++); a.addEventListener('pause',()=>{ if(!a.ended) L.early++; });
  for(const e of ['seeking','play','emptied','ratechange','volumechange']) a.addEventListener(e,()=>L[e]++); })()"""
KIOSK_DRIFT = "typeof G._kioskLast==='number' ? G._kioskLast - window.__lastInput : null"   # 빠른 조사 링크(?fast=1)에서만 숫자


def listen(pg, key, alive):
    """_listen 을 부른다. 듣는 동안 페이지가 다시 로드되면 상태를 읽던 호출이 예외를 던진다(실행 컨텍스트가
    사라진다) — 그것도 '실패'로 돌려준다. 예외로 끝나면 요약도 위생 검사도 찍히지 않기 때문이다."""
    try: return _listen(pg, key, alive)
    except Exception as e:
        try: pg.wait_for_load_state('load', timeout=5000)
        except Exception: pass
        return [f'듣는 동안 예외로 끊겼다(페이지가 다시 로드됐거나 검사 쪽 호출이 실패했다) — {type(e).__name__}: {(str(e).splitlines() or [chr(32)])[0][:90]}'], 0


def _listen(pg, key, alive):
    """key 의 음성을 아무 입력 없이 끝까지 듣는다. (문제 목록, 음성 길이)를 돌려준다 — 목록이 비면 정상.
    alive 는 그동안 변하면 안 되는 화면 상태를 읽는 JS 식(문자열을 돌려주는)이다.
    앞부분 건너뜀은 페이지 안의 시계로 본다: 이 음성은 마지막 실제 입력(클릭·Enter)이 시작시킨 것이므로, 재생
    위치가 그 입력 뒤에 흐른 시간보다 0.25초 넘게 앞서 있으면 앞부분을 건너뛴 것이다. 그래서 입력이 시작시킨
    음성에만 쓴다 — 타이머가 여는 음성(진상 공개 첫 줄)은 대상이 아니다. 한계: 늦게 시작한 만큼 건너뛴 경우
    (1초 늦게, 1초 지점부터)는 이 기준으로는 정상과 구별되지 않는다."""
    if wait_playing(pg, key) is None: return ['재생이 시작되지 않음'], 0
    f0 = pg.evaluate('({t:VOICE.el.currentTime, since:(Date.now()-window.__lastInput)/1000})')
    w0, p0 = time.time(), f0['t']
    why = []
    if p0 > f0['since'] + 0.25:
        why.append(f"앞부분을 건너뜀 — 입력 {f0['since']:.2f}초 뒤인데 재생 위치가 {p0:.2f}초")
    pg.evaluate(LISTEN); a0 = pg.evaluate(alive)
    d = pg.evaluate('isFinite(VOICE.el.duration) ? VOICE.el.duration : 0')
    last, ended, w1 = 0, False, None
    while time.time() - w0 < d + 4:
        s = st(pg)
        if s['file'] != key + '.mp3': why.append(f"다른 파일로 바뀜 {s['file']}"); break
        if s['t'] < last - 0.05: why.append(f"재생 위치가 뒤로 감 {last:.2f}→{s['t']:.2f}초")
        last = s['t']
        if not plain(s): why.append(f"음소거·음량·속도가 바뀜(muted {s['muted']} · volume {s['vol']} · 속도 {s['rate']})")
        if s['ended']: ended = True; w1 = time.time(); break
        if s['paused']: why.append(f"{s['t']:.2f}초에서 멈춤({d:.1f}초 음성)"); break
        if s['n'] != 1: why.append(f"울리는 음성 요소가 {s['n']}개")
        pg.wait_for_timeout(100)
    if not ended and not why: why.append(f'{d:.1f}초 음성이 {last:.2f}초까지 가고 끝나지 않음')
    if ended and last < d - 0.3: why.append(f'{d:.1f}초 음성이 {last:.2f}초에서 끝남')
    if ended and (w1 - w0) < (d - p0) - 0.8: why.append(f'{d - p0:.1f}초 분량이 {w1 - w0:.1f}초 만에 끝남(실시간보다 빠름)')
    pg.wait_for_timeout(2500)      # 끝난 뒤에 저절로 벌어지는 일(다시 재생·줄 넘김·패널 닫힘)을 볼 틈
    L = pg.evaluate('window.__lt ? Object.assign({plays:window.__plays}, window.__lt) : null')
    if L is None: return list(dict.fromkeys(why + ['듣는 동안 페이지가 다시 로드됐다'])), d
    a1 = pg.evaluate(alive)
    if ended and L['ended'] != 1: why.append(f"ended 이벤트 {L['ended']}회")
    if any(L[e] for e in ('early', 'seeking', 'play', 'emptied', 'ratechange', 'volumechange')) or L['plays'] != L['plays0']:
        why.append(f"도중에 재생을 건드림(일시정지 {L['early']}·탐색 {L['seeking']}·재시작 {L['play']}·다시 로드 {L['emptied']}·"
                   f"속도 변경 {L['ratechange']}·음량/음소거 변경 {L['volumechange']}·play() 호출 {L['plays'] - L['plays0']})")
    if st(pg)['n'] != 0: why.append('끝난 뒤에도 음성이 난다')
    if a1 != a0: why.append(f'화면이 저절로 바뀜 {a0} → {a1}')
    k = pg.evaluate(KIOSK_DRIFT)
    if k is not None and not 0 <= k <= 20: why.append(f'무입력 시계가 마지막 입력보다 {k}ms 뒤로 감김')
    return list(dict.fromkeys(why)), d


def until_title(pg, deadline):
    """처음 화면(키오스크 reload)으로 돌아올 때까지 지켜본다. (돌아왔는가, 돌아오기 직전의 상태)."""
    last = None
    while time.time() < deadline:
        try: s = st(pg)
        except Exception:           # reload 도중에는 실행 컨텍스트가 사라진다
            pg.wait_for_timeout(100); continue
        if s['scr'] == 'scr-title':
            # 막 다시 뜬 페이지는 그림 23장을 받는 중이다 — 여기서 곧바로 다음 goto 를 하면 그 요청들이
            # 중단(ERR_ABORTED)돼 위생 검사에 거짓 실패가 난다. 다 받을 때까지 기다린다.
            try: pg.wait_for_load_state('networkidle', timeout=10000)
            except Exception: pass
            return True, last
        last = s; pg.wait_for_timeout(100)
    return False, last


def open_run(pg, run, edit=None):
    """고른 대화의 i번째 줄까지 간다. 진상(REVEAL)은 프롤로그를 넘긴 뒤 그 대화를 직접 연다 — 음성은 사건을
    시작한 클릭으로 이미 풀려 있고, 줄을 넘기는 것은 전부 실제 Enter 다."""
    pg.goto(f"{BASE}?fast={int(run['fast'])}"); pg.wait_for_timeout(400)
    if edit is not None: pg.evaluate(f"CASES.{run['ck']}.{run['arr']}[{edit}].text += ' 부탁드립니다.'")
    pg.click('#scr-title .btn'); pg.click(f"#caseGrid .case-card >> nth={run['ci']}"); settle(pg)
    if 'reveal' in run['arr'].lower():     # REVEAL · fastReveal
        dialog(pg, 'run', [])
        pg.evaluate(f"G.playDialog(G.C.{run['arr']}, ()=>G.show('scr-hub'))")
    for _ in range(run['i']): next_line(pg)


def next_line(pg):
    """다음 줄로 넘긴다 — 타자 효과가 도는 중이면 Enter 두 번(글자 채우기 + 넘기기), 아니면 한 번.
    '도는 중인가'는 키가 도착한 순간의 값(__twAtKey)으로 판단한다: 미리 읽고 보내면 그 사이에 타자 효과가
    저절로 끝나 Enter 가 하나 남고, 대화의 마지막 줄에서는 그 남은 Enter 가 다음 화면에 들어간다."""
    pg.keyboard.press('Enter'); pg.wait_for_timeout(30)
    if pg.evaluate('window.__twAtKey'): pg.keyboard.press('Enter')
    pg.wait_for_timeout(40)


def ask(pg, ans, menu_open=False):
    if not menu_open:
        pg.evaluate(UNLOCK)        # 고른 질문이 단서·증언을 요구할 수 있다 — 상태를 채워 잠금을 푼다(허브에서만)
        pg.click('#talkMenuBtn')
    pg.click(f"#hubGrid .room-card >> nth={ans['pi']}"); pg.click(f"#talkQs .q-btn >> nth={ans['qi']}")


EXITS = {}      # 대화가 끝나 넘어간 화면 → [마지막 줄의 음성이 나던 중에 나간 횟수, 그중 음성이 남은 횟수]
NOPLAY = set()  # 마지막 줄에 음성 파일이 있는데도 재생되지 않은 채 넘어간 화면(건너뜀 사유를 가른다)
TIMER = []      # 타이머가 연 진상 공개 첫 줄(음성 있는 경우)이 입력 없이 재생됐는가


def dialog(pg, tag, problems, first_enter=True):
    """대화 화면을 끝까지 넘기며 줄마다 음성을 검사한다. 진행은 키보드(Enter)만 쓴다.
    마지막 줄의 음성이 나던 중에 대화를 닫았으면, 넘어간 화면(허브·방·추리)에서 끊겼는지도 본다."""
    voiced = had = False
    for _ in range(40):
        scr = active(pg)
        if scr != 'scr-dialog':
            if voiced and scr != 'scr-end':      # 엔딩은 제 낭독이 곧바로 시작되므로 따로 본다
                pg.wait_for_timeout(40); ok = silent(pg)
                e = EXITS.setdefault(scr, [0, 0]); e[0] += 1; e[1] += (not ok)
                if not ok: problems.append(f'{tag} 대화가 끝났는데 {scr} 에서 음성이 계속 난다 {st(pg)}')
            elif had: NOPLAY.add(scr)
            return
        ln = pg.evaluate(LINE)
        voiced = False; had = ln['has']
        if ln['has']:
            ms = wait_playing(pg, ln['key']); voiced = ms is not None
            if ms is None: problems.append(f"{tag} {ln['who']} {ln['key']} 재생 안 됨 {st(pg)}")
            else:
                HEARD.add(ln['key']); LAT['단서' if '단서' in tag else '대화'].append(ms); s0 = st(pg)
                if s0['n'] != 1: problems.append(f"{tag} {ln['key']} 음성이 겹친다 {s0}")
                if not plain(s0): problems.append(f"{tag} {ln['key']} 음소거·음량·속도가 기본값이 아니다 {s0}")
                if first_enter and pg.evaluate('!!G._tw'):
                    # 첫 Enter 는 글자만 마저 채운다 — 음성은 끊기지도, 처음으로 되감기지도 않아야 한다
                    t1 = st(pg)['t']; pg.keyboard.press('Enter'); pg.wait_for_timeout(120); s = st(pg)
                    if not pg.evaluate('window.__twAtKey'):
                        # 상태를 읽고 키를 보내는 사이에 타자 효과가 저절로 끝났다(짧은 줄·부하) — 이 Enter 는 정상적으로
                        # 줄을 넘긴 것이다. 이 줄의 '첫 Enter' 검사는 하지 못했고, 아래의 Enter 를 또 보내면 한 줄을 건너뛴다.
                        continue
                    kept = s['scr'] == 'scr-dialog' and s['cur'] == ln['key'] and not s['paused'] and s['t'] > t1
                    FE.append(kept)
                    if not kept: problems.append(f"{tag} {ln['key']} 첫 Enter 가 음성을 건드림 {s}")
        else:
            pg.wait_for_timeout(60)
            if not silent(pg): problems.append(f"{tag} {ln['who']} 파일 없는 줄인데 소리가 남 {st(pg)}")
        next_line(pg)
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
            pg.click(f'#spots .spot-btn >> nth={si}'); dialog(pg, tag + ' 단서', problems)
        pg.click('#roomBack')


CLOSERS = ['Escape', 'Enter', 'Space', 'click']
NV = [0]            # 음성이 나던 답변을 닫은 횟수(전체 플레이를 통틀어) — 닫는 방법 4종을 이 순번으로 돌린다
ANS_NOPLAY = [0]    # 음성 파일이 있는데 재생되지 않은 답변 수


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
                voiced = False
                if pg.evaluate(f"VOICE.have.has('{k}')"):
                    ms = wait_playing(pg, k)
                    if ms is None: problems.append(f'{tag} 답변 {pk}#{qi} {k} 재생 안 됨 {st(pg)}'); ANS_NOPLAY[0] += 1
                    else:
                        voiced = True; HEARD.add(k); LAT['답변'].append(ms); s0 = st(pg)
                        if s0['n'] != 1: problems.append(f'{tag} 답변 {pk}#{qi} 음성이 겹친다 {s0}')
                        if not plain(s0): problems.append(f'{tag} 답변 {pk}#{qi} 음소거·음량·속도가 기본값이 아니다 {s0}')
                elif not silent(pg): problems.append(f'{tag} 답변 {pk}#{qi} 파일 없는데 소리가 남')
                # 음성이 나던 답변만 '닫으면 음성 정지' 횟수에 든다 — 음성 없는 답변을 닫는 것은 그 검사가 아니다
                if voiced: how = CLOSERS[NV[0] % 4]; NV[0] += 1
                else: how = CLOSERS[n % 4]; n += 1
                if how == 'click': pg.click('#talkAnswer')
                else: pg.keyboard.press(how)
                pg.wait_for_timeout(40)
                shut = pg.evaluate("G.$('talkAnswer').style.display") == 'none' and silent(pg)
                if voiced: closes.setdefault(how, []).append(shut)
                elif not shut: problems.append(f'{tag} 답변 {pk}#{qi} 닫기({how}) — 패널이 남거나 소리가 남')
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
    if active(pg) != 'scr-dialog':
        problems.append(f'{tag} 재현 뒤 진상 공개가 열리지 않음'); TIMER.append(False); return
    ln = pg.evaluate(LINE)
    if ln['has']: TIMER.append(wait_playing(pg, ln['key']) is not None)   # 음성 없는 첫 줄은 세지 않는다(공허한 통과 방지)
    dialog(pg, tag + ' 진상', problems)


def play(pg, idx, fast, url=None):
    start(pg, idx, fast, url)
    tag = f'{pg.evaluate("G.caseKey")}/{"빠른" if fast else "표준"}'
    problems, closes = [], {}
    dialog(pg, tag + ' 프롤로그', problems)
    clues(pg, tag, problems)
    talks(pg, tag, problems, closes)
    deduce(pg, tag, problems, regroup=not fast)
    sim_then_reveal(pg, tag, problems)
    check(f'{tag} 모든 대사가 제 파일로 재생(파일 없는 줄은 무음)', not problems, problems[:3])
    check(f'{tag} 엔딩 도달 · 엔딩 글 낭독(파일 없으면 무음)', active(pg) == 'scr-end' and ending_voice(pg), st(pg))
    return closes


def ending_voice(pg):
    k = pg.evaluate("VOICE.key('내레이션', G.C.ending.text)")
    if not pg.evaluate(f"VOICE.have.has('{k}')"): return silent(pg)
    ms = wait_playing(pg, k)
    if ms is None: return False
    HEARD.add(k); LAT['대화'].append(ms)
    return plain(st(pg))      # 엔딩 글도 음소거 아님 · 음량 1 · 속도 1 로 시작해야 한다


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
    try: from playwright.sync_api import sync_playwright
    except ImportError:
        print('playwright 가 없다 — pip install playwright (브라우저는 깔린 것을 쓴다)'); return 2
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
        if TIMER: check(f'타이머가 연 진상 공개 첫 줄도 입력 없이 재생 ({len(TIMER)}회)', all(TIMER))
        else: skip('타이머가 연 진상 공개 첫 줄도 입력 없이 재생', '진상 공개 첫 줄에 음성이 있는 사건이 없다')
        for scr, nm in (('scr-hub', '허브'), ('scr-room', '방'), ('scr-deduce', '추리')):
            e = EXITS.get(scr)
            if e: check(f'음성이 나던 중에 대화를 닫으면 {nm} 화면에서는 끊겨 있다 ({e[0]}회)', e[1] == 0, f'{e[1]}회 남음')
            else: skip(f'음성이 나던 중에 대화를 닫으면 {nm} 화면에서는 끊겨 있다',
                       '마지막 줄의 음성이 재생되지 않아 확인하지 못했다(위 실패 참고)' if scr in NOPLAY
                       else f'{nm} 화면으로 끝나는 대화의 마지막 줄에 음성이 없다')
        # 시작 지연은 묶음별 '중앙값'으로 본다 — 한 줄 한 줄의 최댓값은 부하에 따라 1초 가까이 튀어 기준으로 못 쓴다.
        # 재는 구간은 '검사가 그 줄을 보기 시작한 때 → 재생 위치가 움직이는 것을 확인한 때'다(줄이 화면에 뜬 순간부터가 아니다).
        # 표본이 8개보다 적은 묶음은 판단하지 않는다 — 두세 개의 중앙값은 사실상 최댓값이라 부하 한 번에 넘는다.
        meds = {g: (sorted(v)[len(v) // 2], len(v)) for g, v in LAT.items() if len(v) >= 8}
        if meds:
            check('검사가 줄을 본 뒤 재생이 확인되기까지 — 묶음별 중앙값 ' + ' · '.join(f'{g} {m:.0f}ms({n}회)' for g, (m, n) in meds.items())
                  + f" (모두 500ms 안 · localhost · 한 줄 최대 {max(max(v) for v in LAT.values() if v):.0f}ms)",
                  all(m < 500 for m, _ in meds.values()), '중앙값이 500ms 를 넘는 묶음이 있다')
        for g, v in LAT.items():
            if len(v) < 8: skip(f'검사가 줄을 본 뒤 재생이 확인되기까지 — {g} 묶음의 중앙값 500ms 안', f'표본이 {len(v)}개뿐이다(8개부터 판단한다)')
        if FE: check(f'타자 효과 도중의 첫 Enter 는 글자만 채운다 — 음성은 끊기지도 되감기지도 않는다 ({len(FE)}회)', all(FE), f'{FE.count(False)}회 어김')
        else: skip('타자 효과 도중의 첫 Enter 는 글자만 채운다 — 음성은 끊기지도 되감기지도 않는다',
                   '타자 효과가 도는 동안 Enter 가 도착한 줄이 없었다(느린 환경에서는 그 전에 타자 효과가 끝난다)')

        section('W3 정지 경로')
        for how in CLOSERS:
            v = closes.get(how, [])
            if v: check(f'음성이 나던 답변 닫기 — {how} ({len(v)}회) 패널 닫힘·음성 정지', all(v), f'{v.count(False)}회 남음')
            else: skip(f'음성이 나던 답변 닫기 — {how} 패널 닫힘·음성 정지',
                       '답변 음성이 재생되지 않아 확인하지 못했다(위 실패 참고)' if ANS_NOPLAY[0] else '이 방법으로 닫을 음성 있는 답변이 남지 않았다')
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
        check('허브 [로비로] — 로비·무음', active(pg) == 'scr-lobby' and silent(pg), st(pg))
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
        else:
            for nm in ('닫았다가 다시 물으면 처음부터 다시 재생', '답변이 떠 있는 채로 다시 눌러도 처음부터 재생'):
                skip(nm, '음성 있는 심문 답변이 하나도 없다')

        section('W5 음소거 연동')
        if ans:     # W4 의 마지막 상태(답변이 떠서 재생 중)에서 이어 간다
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
            # 음성 요소가 아직 없을 때 사운드를 끈 경우. 사운드 버튼은 허브에 있고 프롤로그가 먼저 요소를 만들기 때문에,
            # 프롤로그가 통째로 무음인 사건에서만 닿는 경로다 — 이 페이지 안에서 프롤로그를 고쳐(W6 과 같은 방식) 만든다.
            pg.goto(BASE + '?fast=0'); pg.wait_for_timeout(400)
            pg.evaluate(f"CASES[Object.keys(CASES)[{ans['ci']}]].PROLOGUE.forEach(l=>{{ l.text+=' 부탁드립니다.'; }})")
            pg.click('#scr-title .btn'); pg.click(f"#caseGrid .case-card >> nth={ans['ci']}"); settle(pg)
            dialog(pg, 'W5', [])
            no_el = active(pg) == 'scr-hub' and pg.evaluate('VOICE.el===null')
            pg.click('#sndBtn')
            ask(pg, ans); on_air = wait_playing(pg, ka) is not None; s_ = st(pg)
            check('첫 음성이 나기 전에 사운드를 꺼도 첫 음성부터 muted', no_el and on_air and s_['muted'] is True, (no_el, s_))
        else:
            for nm in ('사운드 끄면 음성도 muted, 다시 켜면 풀린다', '음량은 파일에 구워져 있다 — 재생 중 volume 은 1 그대로',
                       '첫 음성이 나기 전에 사운드를 꺼도 첫 음성부터 muted'):
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
        prob = []
        pg.goto(BASE + '?fast=1'); pg.wait_for_timeout(400)
        kb('#scr-title .btn'); kb('#caseGrid .case-card', 0); settle(pg)
        dialog(pg, 'W7 프롤로그', prob)
        for ri, rk in enumerate(pg.evaluate('Object.keys(G.C.ROOMS)')):
            kb('#hubGrid .room-card', ri)
            for si in pg.evaluate(f"G.C.ROOMS['{rk}'].spots.map((s,i)=>s.clue?i:-1).filter(i=>i>=0)"):
                kb('#spots .spot-btn', si); dialog(pg, 'W7 단서', prob)
            kb('#roomBack')
        for _ in range(2):
            for pi, pk in enumerate(pg.evaluate('Object.keys(G.C.PEOPLE)')):
                kb('#talkMenuBtn'); kb('#hubGrid .room-card', pi)
                for qi in range(pg.evaluate(f"G.C.PEOPLE['{pk}'].qs.length")):
                    if pg.evaluate(f"document.querySelectorAll('#talkQs .q-btn')[{qi}].className.match(/locked|asked/)!==null"): continue
                    kb('#talkQs .q-btn', qi)
                    k = pg.evaluate(f"(()=>{{const p=G.C.PEOPLE['{pk}']; return VOICE.key(p.name.split(' · ')[0], p.qs[{qi}].a)}})()")
                    if pg.evaluate(f"VOICE.have.has('{k}')"):
                        if wait_playing(pg, k) is None: prob.append(f'W7 답변 {pk}#{qi}')
                        elif not plain(st(pg)): prob.append(f'W7 답변 {pk}#{qi} 음소거·음량·속도가 기본값이 아니다')
                    pg.keyboard.press('Enter'); pg.wait_for_timeout(50)
                    if not silent(pg): prob.append(f'W7 답변 닫기 {pk}#{qi}')
                kb('#talkBack'); kb('#talkMenuBtn')
        kb('#deduceBtn'); dialog(pg, 'W7 추리 도입', prob)
        for _ in range(pg.evaluate('G.DQ.length')):
            pg.keyboard.press(str(pg.evaluate('G.DQ[G.deduceIdx].ans') + 1)); pg.wait_for_timeout(1750)
        sim_then_reveal(pg, 'W7', prob)
        check('마우스 없이 엔딩까지 — 음성 재생·정지 정상', active(pg) == 'scr-end' and not prob, (active(pg), prob[:3]))

        section('W8 키오스크 무입력 복귀')
        DRIFT = 'G._kioskLast - window.__lastInput'    # 무입력 시계가 마지막 실제 입력보다 얼마나 뒤에 있나(ms)
        cands = pg.evaluate(PICK_FAST0)
        if cands:
            for kc in cands:       # 3초 한도보다 넉넉히 긴 음성으로 시작하는 사건을 찾는다
                start(pg, kc, True); t_in = time.time()
                k0 = pg.evaluate(LINE)['key']; was = wait_playing(pg, k0) is not None
                d = pg.evaluate('VOICE.el && isFinite(VOICE.el.duration) ? VOICE.el.duration : 0')
                if d >= 6: break
            # ① 음성이 나는 도중에 한도(3초)가 찬다 — 음성이 울리고 있다고 복귀를 미루면 안 된다
            pg.evaluate('G.KIOSK_WARN=1500; G.KIOSK_OUT=3000')
            pg.wait_for_timeout(1200); drift = pg.evaluate(DRIFT)
            back, last = until_title(pg, t_in + 3 + 2.5)      # 틱이 1초 간격이라 3~4초 사이에 reload 된다(+다시 뜨는 시간)
            sounding = bool(last) and last['cur'] == k0 and not last['paused'] and not last['ended']   # 돌아가기 직전까지 음성이 나고 있었다
            check('음성이 시작돼도 무입력 시계는 마지막 실제 입력 시각 그대로다', was and 0 <= drift <= 20, f'{drift}ms 어긋남')
            if d >= 6:
                check(f'음성이 나는 도중이어도({d:.1f}초 음성·한도 3초) 무입력이면 처음 화면으로 돌아간다',
                      was and back and sounding and pg.evaluate('VOICE.el===null'), (back, last))
            else:
                skip('음성이 나는 도중이어도 무입력이면 처음 화면으로 돌아간다', '빠른 조사 첫 줄의 음성이 6초보다 짧다')
            # ② 음성보다 긴 한도 — 음성이 끝나는 순간에도 시계를 되감지 않아야 한도 직후에 돌아간다
            start(pg, kc, True); t_in = time.time()
            was = wait_playing(pg, k0) is not None
            pg.evaluate(f'G.KIOSK_WARN={int((d + 1.5) * 1000)}; G.KIOSK_OUT={int((d + 3) * 1000)}')
            ended = False
            while time.time() < t_in + d + 2 and not ended:
                ended = pg.evaluate('!!VOICE.el && VOICE.el.ended'); pg.wait_for_timeout(100)
            pg.wait_for_timeout(400); drift = pg.evaluate(DRIFT)
            back, last = until_title(pg, t_in + d + 3 + 2.5)
            check(f'음성이 끝난 뒤에도({d:.1f}초) 무입력 시계는 그대로이고, 한도가 차면 처음 화면으로 돌아간다',
                  was and ended and 0 <= drift <= 20 and back and pg.evaluate('VOICE.el===null'),
                  (f'끝남 {ended}', f'{drift}ms 어긋남', f'복귀 {back}', last))
        else:
            for nm in ('음성이 시작돼도 무입력 시계는 마지막 실제 입력 시각 그대로다', '음성이 나는 도중이어도 무입력이면 처음 화면으로 돌아간다',
                       '음성이 끝난 뒤에도 무입력 시계는 그대로이고, 한도가 차면 처음 화면으로 돌아간다'):
                skip(nm, '빠른 조사 첫 줄에 음성이 있는 사건이 없다')
            start(pg, 0, True)
            pg.evaluate('G.KIOSK_WARN=1500; G.KIOSK_OUT=3000')
            back, last = until_title(pg, time.time() + 5.5)
            check('무입력이면 처음 화면으로 돌아간다(음성 없는 줄에서)', back, last)

        section('W9 끝까지 듣기')
        try:
            TAIL = '한 번만·끝까지·재생 위치가 입력 뒤 흐른 시간을 0.25초 넘게 앞서지 않음·음소거/음량/속도 그대로·끝난 뒤에도 화면 그대로'
            ON_LINE = "JSON.stringify([document.querySelector('.screen.active').id, G.dlgIdx])"
            def heard(name, res, why_skip):
                if res is None: skip(f'아무 입력 없이 끝까지 듣기 — {name}: {TAIL}', why_skip)
                else: check(f'아무 입력 없이 끝까지 듣기 — {name}({res[1]:.1f}초): {TAIL}', not res[0], res[0])
            # ① 대화의 첫 줄, ② 같은 대화의 그다음 줄, ③ 단서 설명 — 한 번의 플레이에서 이어서 듣는다.
            # 빠른 조사 링크(?fast=1)의 첫 줄을 먼저 고른다 — 그래야 이 세 줄에서도 무입력 시계를 본다. 그 안에서는 긴 것.
            firsts = sorted(pg.evaluate(PICK_FIRSTS), key=lambda x: (not x['fast'], -DUR.get(x['key'], 0)))
            r1 = r2 = r3 = None
            f = firsts[0] if firsts else {'ci': 0, 'fast': True, 'key': None}     # 첫 줄이 전부 무음이어도 단서는 듣는다
            start(pg, f['ci'], f['fast'])
            if f['key']:
                r1 = listen(pg, f['key'], ON_LINE)
                nxt = pg.evaluate("""(()=>{ const l=G.dlgQueue[G.dlgIdx+1]; if(!l) return null;
                  const k=VOICE.key(l.name.split(' · ')[0], l.text); return VOICE.have.has(k)?k:null; })()""")
                if nxt and active(pg) == 'scr-dialog':
                    next_line(pg)
                    r2 = listen(pg, nxt, ON_LINE)
            dialog(pg, 'W9', [])        # 남은 줄을 넘겨 허브로
            if active(pg) == 'scr-hub':
                for ri, rk in enumerate(pg.evaluate('Object.keys(G.C.ROOMS)')):
                    pg.click(f'#hubGrid .room-card >> nth={ri}')
                    for si in pg.evaluate(f"G.C.ROOMS['{rk}'].spots.map((s,i)=>s.clue?i:-1).filter(i=>i>=0)"):
                        pg.click(f'#spots .spot-btn >> nth={si}')
                        ln = pg.evaluate(LINE) if active(pg) == 'scr-dialog' else None
                        if ln and ln['has']: r3 = listen(pg, ln['key'], ON_LINE); break
                        dialog(pg, 'W9', [])
                    if r3: break
                    pg.click('#roomBack')
            no_first = '프롤로그 첫 줄에 음성이 있는 사건이 없다'
            heard('대화의 첫 줄', r1, no_first)
            heard('대화의 그다음 줄', r2, no_first if not f['key'] else '음성 있는 첫 줄 바로 뒤에 음성 있는 줄이 없다')
            heard('단서 설명 한 줄', r3, '이 사건·이 모드에서 첫 줄부터 음성이 있는 단서를 찾지 못했다(다른 모드의 단서 설명에는 음성이 있을 수 있다)')
            # ④ 심문 답변 — 빠른 조사 링크에서 듣는다(무입력 시계도 함께 본다)
            answers = sorted(pg.evaluate(PICK_ANSWERS), key=lambda x: -DUR.get(x['key'], 0))
            r4 = None
            if answers:
                la = answers[0]; start(pg, la['ci'], True); dialog(pg, 'W9', [])
                pg.evaluate(UNLOCK); pg.click('#talkMenuBtn'); pg.click(f"#hubGrid .room-card >> nth={la['pi']}")
                pg.click(f"#talkQs .q-btn >> nth={la['qi']}")
                r4 = listen(pg, la['key'], "JSON.stringify([document.querySelector('.screen.active').id, G.$('talkAnswer').style.display])")
            heard('심문 답변 하나', r4, '음성 있는 심문 답변이 하나도 없다')
            # ⑤ 엔딩 글 — 빠른 조사로 엔딩까지 가서 듣는다
            r5 = None
            if end['has']:
                start(pg, end['ci'], True); dialog(pg, 'W9', []); pg.evaluate(ready)
                pg.click('#deduceBtn'); dialog(pg, 'W9', [])
                for _ in range(pg.evaluate('G.DQ.length')):
                    pg.keyboard.press(str(pg.evaluate('G.DQ[G.deduceIdx].ans') + 1)); pg.wait_for_timeout(1750)
                sim_then_reveal(pg, 'W9', [])
                r5 = listen(pg, pg.evaluate("VOICE.key('내레이션', G.C.ending.text)"), "JSON.stringify([document.querySelector('.screen.active').id])")
            heard('엔딩 글', r5, '엔딩 글에 음성이 있는 사건이 없다')
        except Exception as e:
            # 듣던 줄 밖에서(다음 단계로 가던 중에) 페이지가 사라진 경우 — 남은 듣기는 하지 못했다
            check('W9 를 끝까지 돌렸다(도중에 예외가 나지 않았다 — 페이지가 다시 로드되면 난다)', False, f'{type(e).__name__}: {(str(e).splitlines() or [chr(32)])[0][:120]}')

        section('W10 위생')
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
        print(f'PASS(부분) — 실패는 없지만 위 {len(SKIP)}건은 검사하지 못했다 — 사유는 각 줄에(건너뜀은 통과가 아니다)')
        return 3
    print('PASS — 대사 음성 검증 전부 통과')
    return 0


if __name__ == '__main__':
    sys.exit(main())

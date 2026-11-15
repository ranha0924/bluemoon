#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대사 음성 도구 — tools/voice/(대본·배역·원본) → assets/voice/*.mp3 + index.html 의 VOICE_HAVE

게임은 실행 중에 어떤 API 도 부르지 않는다. 음성은 ElevenLabs TTS 로 '한 번' 합성해
파일로 커밋해 둔 것이고, 이 도구가 그 합성·검수·인코딩·정합성 검사를 맡는다.

  python3 tools/build-voice.py check      # 정합성 검사 (API 키 불필요, 커밋 전 필수)
  python3 tools/build-voice.py encode     # 원본 → assets/voice/*.mp3 (API 키 불필요, 반복 가능)
  python3 tools/build-voice.py manifest   # index.html 의 VOICE_HAVE 한 줄 갱신
  python3 tools/build-voice.py prune      # 탑재 대상을 지금 대사에 맞춘다 — 주인 없는 파일은 지우고 대본에서 내리며,
                                          #   대사가 원래대로 돌아온 줄은 되살린다(그 뒤 encode → manifest)
  python3 tools/build-voice.py fetch      # 원본 합성 (ELEVENLABS_API_KEY 필요, 표준 라이브러리만 사용)
  python3 tools/build-voice.py probe      # 탑재 파일을 받아써 낭독문과 낱말이 다르게 들리는 줄을 찾는다 (API 키 필요)

파일
  tools/voice/script.json   대사별 {key, who, src, text(화면 표기), tts(낭독문), ship}
                            tts 는 숫자·단위를 한글로 풀고(60℃→육십 도) 지문은 연기 태그로 바꾼 것.
                            ship:false 는 게임에 싣지 않는 보험용 원본(탐정의 질문 선택지).
  tools/voice/cast.json     화자 → ElevenLabs 목소리·모델·설정
  tools/voice/masters/      API 가 준 원본 mp3 (재인코딩의 출발점 — API 키가 없어도 음량·비트레이트를 다시 맞출 수 있다)
  tools/voice/takes.json    합성·인코딩 기록 — 시드·길이·음성→텍스트 역검증 결과, 그리고 원본과 탑재 파일의
                            sha256. check 가 이것으로 '파일이 기록해 둔 그 합성·인코딩 결과인가'를 본다
                            (이름만 맞고 내용이 뒤바뀐 파일, 대본·배역을 바꿔 놓고 다시 합성하지 않은
                            원본을 잡는다). 기록 자체가 기준이므로, 파일과 기록을 함께 바꾸면 통과한다 —
                            소리가 정말 그 문장인지는 받아쓰기(fetch 의 역검증, probe)와 사람의 귀가 본다.

키 = FNV-1a 32bit( UTF-8( 화자 + '|' + [[ ]] 를 벗긴 대사 ) ) — index.html 의 VOICE.key 와 같다.
대사를 고치면 키가 달라져 그 줄은 무음이 된다. 재합성은 API 키가 있을 때만 가능하므로,
check 는 '음성이 사라진 줄'을 실패로 알린다(감수하려면 prune → manifest → check --allow-unvoiced).
"""
import argparse, difflib, hashlib, json, os, re, shutil, subprocess, sys, time, uuid
import urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'index.html'
VDIR = ROOT / 'tools' / 'voice'
SCRIPT, CAST, TAKES, MASTERS = VDIR / 'script.json', VDIR / 'cast.json', VDIR / 'takes.json', VDIR / 'masters'
OUT = ROOT / 'assets' / 'voice'
API = 'https://api.elevenlabs.io'
HAVE_RE = re.compile(r'^const VOICE_HAVE = "([0-9a-f ]*)";$', re.M)
# 인코딩 목표 — 파일에 굽는다(게임은 volume 을 건드리지 않는다).
# 모노 파일은 양쪽 스피커로 나가 측정값보다 약 3 LU 크게 들린다: 모노 측정 -21 LUFS ≈ 스테레오 환산 -18 LUFS.
# 배경음악은 BGM.VOL .14 를 지나 약 -30 LUFS 이므로 음성이 12 LU 가량 위에 온다.
TARGET_I, PEAK_DB, BITRATE = -21.0, -1.5, '48k'

for _s in (sys.stdout, sys.stderr):   # 한국어 윈도우 cp949 리다이렉트에서 '—' 로 죽지 않게
    try: _s.reconfigure(errors='replace')
    except AttributeError: pass


def die(msg):
    print('build-voice: ' + msg, file=sys.stderr)
    sys.exit(2)


def plain(s):
    return s.replace('[[', '').replace(']]', '')


def fnv(who, text):
    h = 0x811c9dc5
    for b in (who + '|' + plain(text)).encode('utf-8'):
        h = ((h ^ b) * 0x01000193) & 0xffffffff
    return f'{h:08x}'


def load(p):
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else None


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def script():
    s = load(SCRIPT)
    if s is None: die(f'{SCRIPT.relative_to(ROOT)} 가 없다')
    for e in s:
        if e['key'] != fnv(e['who'], e['text']):
            die(f"script.json 의 key 가 who|text 와 어긋난다: {e['key']} ({e['who']})")
    if len({e['key'] for e in s}) != len(s): die('script.json 에 같은 key 가 두 번 있다')
    return s


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]


def params(v, cast):
    """합성 결과를 좌우하는 설정 — takes.json 에 남겨, 설정만 바꾸고 다시 합성하지 않은 원본을 check 가 잡는다."""
    return {'stability': v.get('stability', 0.5), 'similarity_boost': v.get('similarity_boost', 0.75),
            'language_code': cast.get('language_code'), 'output_format': cast.get('output_format')}


def have_now():
    m = HAVE_RE.search(SRC.read_text(encoding='utf-8'))
    if not m: die('index.html 에서 const VOICE_HAVE = "…"; 한 줄을 찾지 못했다')
    return set(m.group(1).split())


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def need_ffmpeg():
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): die('ffmpeg/ffprobe 가 필요하다')


def duration(p):
    r = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)], text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0


# ---------------------------------------------------------------- 페이지에서 대사 열거
# 엔진이 실제로 계산하는 키를 그대로 받는다(해시 구현은 페이지가 원본, 파이썬은 대조용).
ENUM_JS = r"""(()=>{ const out=[], W=n=>n.split(' · ')[0];
  const add=(src,who,text,spoken)=>out.push({src, who, text, key:VOICE.key(who,text), spoken});
  for(const ck in CASES){ const C=CASES[ck];
    for(const nm of ['PROLOGUE','fastPrologue','REVEAL','fastReveal'])
      (C[nm]||[]).forEach((l,i)=>add(ck+'.'+nm+'.'+i, W(l.name), l.text, true));
    for(const nm of ['deduceIntro','regroup']) if(C[nm]) add(ck+'.'+nm, W(C[nm].name), C[nm].text, true);
    for(const pk in C.PEOPLE) C.PEOPLE[pk].qs.forEach((q,i)=>{
      add(ck+'.PEOPLE.'+pk+'.'+i+'.a', W(C.PEOPLE[pk].name), q.a, true);
      add(ck+'.PEOPLE.'+pk+'.'+i+'.q', '한세인', q.q, false); });
    for(const k in C.CLUES){ const c=C.CLUES[k];
      add(ck+'.CLUES.'+k+'.desc', '단서', c.desc, true);
      if(c.fast) add(ck+'.CLUES.'+k+'.fast', '단서', c.fast, true); }
    if(C.ending&&C.ending.text) add(ck+'.ending', '내레이션', C.ending.text, true);
  } return out; })()"""


def chrome():
    for p in (os.environ.get('BIB_CHROME'), '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', '/opt/pw-browsers/chromium'):
        if p and os.path.exists(p): return p
    return None   # playwright 가 스스로 찾게 둔다


def page_lines():
    """index.html 을 헤드리스 크롬으로 열어 대사를 열거한다 (file:// — 서버 불필요).
    spoken=True 는 게임이 소리 내어 읽는 범위(대화 화면의 모든 줄·심문 답변·엔딩 글),
    False 는 심문 화면의 질문 선택지(탐정의 질문 — 원본만 있고 싣지 않는다)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        die('playwright 가 필요하다 — pip install playwright')
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=chrome())
        pg = b.new_page()
        pg.goto(SRC.as_uri()); pg.wait_for_function('typeof VOICE==="object"')
        lines = pg.evaluate(ENUM_JS)
        b.close()
    for l in lines:
        if l['key'] != fnv(l['who'], l['text']):
            die(f"페이지의 VOICE.key 와 파이썬 대조 구현이 어긋난다: {l['src']}")
    return lines


# ---------------------------------------------------------------- check
def cmd_check(a):
    need_ffmpeg()
    bad, warn = [], []
    lines = page_lines()
    spoken = {}
    for l in lines:
        if l['spoken']: spoken.setdefault(l['key'], l)
    sc = script()
    by_key = {e['key']: e for e in sc}
    cast = load(CAST) or {}
    have = have_now()
    files = {p.stem for p in OUT.glob('*.mp3')} if OUT.is_dir() else set()
    extra = sorted(p.name for p in OUT.iterdir() if p.suffix != '.mp3') if OUT.is_dir() else []

    if extra: bad.append(f'assets/voice 에 mp3 가 아닌 파일: {extra[:5]}')
    if have != files:
        bad.append(f'VOICE_HAVE 와 assets/voice/*.mp3 가 어긋난다 — 목록에만 {sorted(have - files)[:5]}, '
                   f'파일에만 {sorted(files - have)[:5]}  → python3 tools/build-voice.py manifest')
    for k in sorted(files):
        e = by_key.get(k)
        if not e: bad.append(f'{k}.mp3 — script.json 에 대본이 없다'); continue
        if not e.get('ship'): bad.append(f'{k}.mp3 — ship:false 인 대사가 assets/voice 에 있다')
        if not (MASTERS / f'{k}.mp3').is_file(): bad.append(f'{k}.mp3 — tools/voice/masters 에 원본이 없다')
        if k not in spoken:
            bad.append(f"{k}.mp3 — 이 대사가 index.html 에서 사라졌거나 바뀌었다({e['who']}: {plain(e['text'])[:24]}…)"
                       '  → python3 tools/build-voice.py prune')
        p = OUT / f'{k}.mp3'
        r = run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                 'stream=codec_name,channels,sample_rate:format=duration', '-of', 'json', str(p)], text=True)
        try:
            j = json.loads(r.stdout); st = j['streams'][0]; d = float(j['format']['duration'])
            cps = len(re.sub(r'[^0-9A-Za-z가-힣]', '', plain(e['text'] if e else ''))) / d if d else 0
            if st['codec_name'] != 'mp3' or st['channels'] != 1: bad.append(f'{k}.mp3 — 모노 mp3 가 아니다: {st}')
            if not 0.6 < d < 40: bad.append(f'{k}.mp3 — 길이가 이상하다: {d:.2f}s')
            elif e and not 2.5 < cps < 9: warn.append(f'{k}.mp3 — 말속도가 이상하다: {cps:.1f} 자/초')
        except Exception:
            bad.append(f'{k}.mp3 — 디코드 실패(손상·LFS 포인터?)')
    takes = load(TAKES) or {}
    for e in sc:
        k = e['key']; v = cast.get('voices', {}).get(e['who'])
        if not v: bad.append(f"cast.json 에 화자가 없다: {e['who']}")
        if not e.get('tts', '').strip(): bad.append(f"낭독문(tts)이 비었다: {k}")
        m = MASTERS / f'{k}.mp3'
        if not m.is_file(): continue
        t = takes.get(k)
        if not t: bad.append(f'{k} — 원본은 있는데 takes.json 에 합성 기록이 없다'); continue
        # 파일 이름은 대사의 키일 뿐이다 — 내용이 정말 그 대사의 것인지는 기록해 둔 해시로 본다.
        if sha(m) != t.get('sha256'): bad.append(f'{k} — 원본이 합성 기록과 다르다(뒤바뀜·손상?)')
        if t.get('tts') != e.get('tts'): bad.append(f'{k} — 원본을 합성한 뒤 낭독문(tts)이 바뀌었다 — 다시 합성하거나 대본을 되돌린다')
        if v and (t.get('voice_id') != v.get('voice_id') or t.get('model') != cast.get('model')
                  or t.get('params') != params(v, cast)):
            bad.append(f"{k} — 원본을 합성한 뒤 배역({e['who']})의 목소리·모델·설정이 바뀌었다 — 다시 합성하거나 cast.json 을 되돌린다")
        dst = OUT / f'{k}.mp3'
        if dst.is_file() and sha(dst) != t.get('asset'):
            bad.append(f'{k}.mp3 — 탑재 파일이 인코딩 기록과 다르다(뒤바뀜·손상?)  → python3 tools/build-voice.py encode')
    unvoiced = [l for k, l in spoken.items() if k not in files]
    for l in unvoiced:
        back = by_key.get(l['key'], {}).get('pruned') or (by_key.get(l['key'], {}).get('ship') and (MASTERS / f"{l['key']}.mp3").is_file())
        (warn if a.allow_unvoiced and not back else bad).append(
            f"음성 없는 대사: {l['src']} ({l['who']}: {plain(l['text'])[:28]}…)"
            + ('  → 원본이 있다: python3 tools/build-voice.py prune → encode → manifest' if back else ''))
    on_page = {l['key'] for l in lines}
    for e in sc:
        if not e.get('ship') and not e.get('pruned') and e['key'] not in on_page:
            warn.append(f"싣지 않는 원본의 대사가 index.html 에서 바뀌었다: {e['key']} ({e['who']}: {plain(e['text'])[:24]}…)")

    total = sum(p.stat().st_size for p in OUT.glob('*.mp3')) if OUT.is_dir() else 0
    print(f'대사 {len(spoken)}줄 중 음성 {len(spoken) - len(unvoiced)}줄 · 파일 {len(files)}개 {total / 1e6:.2f} MB '
          f'· 대본 {len(sc)}줄(게임 탑재 {sum(1 for e in sc if e.get("ship"))}) '
          f'· 원본 {len(list(MASTERS.glob("*.mp3"))) if MASTERS.is_dir() else 0}개')
    for w in warn: print('  주의  ' + w)
    for b_ in bad: print('  FAIL  ' + b_)
    if bad:
        print(f'FAIL — {len(bad)}건'); return 1
    print('PASS — 대사 음성 정합성 통과')
    return 0


# ---------------------------------------------------------------- manifest / prune
def cmd_manifest(a):
    files = sorted(p.stem for p in OUT.glob('*.mp3')) if OUT.is_dir() else []
    html = SRC.read_bytes().decode('utf-8')
    if len(HAVE_RE.findall(html)) != 1: die('index.html 의 const VOICE_HAVE = "…"; 가 정확히 1줄이 아니다')
    new = HAVE_RE.sub(lambda m: 'const VOICE_HAVE = "' + ' '.join(files) + '";', html)
    if new != html: SRC.write_bytes(new.encode('utf-8'))
    print(f'VOICE_HAVE — {len(files)}개' + ('' if new != html else ' (변경 없음)'))
    return 0


def cmd_prune(a):
    """대본의 탑재 대상을 지금의 index.html 에 맞춘다(양방향).
    - 대사가 바뀌어 주인이 없어진 줄: assets/voice 에서 지우고 대본에서 내린다(ship:false + pruned:true) —
      그러지 않으면 다음 encode 가 방금 지운 파일을 되살린다.
    - 내렸던 줄의 대사가 원래대로 돌아왔으면 되살린다 — 이어서 encode → manifest 를 돌리면 파일이 돌아온다."""
    spoken = {l['key'] for l in page_lines() if l['spoken']}
    sc = script()
    revived = [e for e in sc if e.get('pruned') and e['key'] in spoken]
    for e in revived:
        e['ship'] = True; e.pop('pruned')
    retired = [e for e in sc if e.get('ship') and e['key'] not in spoken]
    for e in retired:
        e['ship'] = False; e['pruned'] = True
    ship = {e['key'] for e in sc if e.get('ship')}
    gone = [p for p in sorted(OUT.glob('*.mp3')) if p.stem not in ship] if OUT.is_dir() else []
    for p in gone:
        print('삭제  ' + str(p.relative_to(ROOT))); p.unlink()
    if retired or revived: dump(SCRIPT, sc)
    print(f'파일 {len(gone)}개 삭제 · 대본에서 내림 {len(retired)}줄 · 되살림 {len(revived)}줄 — 원본(tools/voice/masters)은 '
          '그대로다. 이어서 ' + ('encode → ' if revived else '') + 'manifest 를 돌린다.')
    return 0


# ---------------------------------------------------------------- encode
def loud(paths):
    """여러 파일을 이어 붙인 것의 통합 음량(LUFS)·트루피크(dBTP) — 화자 단위로 한 번에 잰다."""
    ins = []
    for p in paths: ins += ['-i', str(p)]
    flt = ''.join(f'[{i}:a]' for i in range(len(paths))) + f'concat=n={len(paths)}:v=0:a=1,ebur128=peak=true'
    r = run(['ffmpeg', '-hide_banner', '-nostats', *ins, '-filter_complex', flt, '-f', 'null', '-'], text=True)
    tail = r.stderr[r.stderr.rfind('Summary:'):]
    i = re.search(r'I:\s*(-?[\d.]+) LUFS', tail); tp = re.search(r'Peak:\s*(-?[\d.]+) dBFS', tail)
    if not i or not tp: die('음량 측정 실패:\n' + r.stderr[-400:])
    return float(i.group(1)), float(tp.group(1))


def trim_points(p):
    """앞뒤 무음 구간 — 앞은 60ms, 뒤는 180ms 만 남기고 자른다."""
    r = run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(p), '-af', 'silencedetect=noise=-50dB:d=0.08', '-f', 'null', '-'], text=True)
    d = duration(p)
    st = [float(x) for x in re.findall(r'silence_start: (-?[\d.]+)', r.stderr)]
    en = [float(x) for x in re.findall(r'silence_end: (-?[\d.]+)', r.stderr)]
    a, b = 0.0, d
    if st and st[0] <= 0.01 and en: a = max(0.0, en[0] - 0.06)
    if st and (len(en) < len(st) or en[-1] >= d - 0.02): b = min(d, st[-1] + 0.18)
    return (a, b) if b - a > 0.5 else (0.0, d)


def speaker_gain(who, sc_all, extra=()):
    """화자 단위 고정 이득(dB) — 그 화자의 원본 '전부'(싣지 않는 줄·내린 줄 포함)를 이어 붙여 잰다.
    줄마다 정규화하면 속삭임과 외침이 같은 크기가 되어 연기가 눌리고, 탑재하는 줄만으로 재면 한 줄을
    내리거나 되살릴 때마다 같은 화자의 다른 파일까지 바뀐다."""
    srcs = [MASTERS / f"{e['key']}.mp3" for e in sc_all if e['who'] == who]
    srcs = [p for p in srcs if p.is_file()] + list(extra)
    i, tp = loud(srcs)
    return TARGET_I - i, i, tp


def encode_one(src, dst, gain):
    """원본 하나를 탑재 형식으로 — 앞뒤 무음 다듬기 → 고정 이득 → 리미터(이득 뒤 봉우리가 상한을 넘을 때만 눌린다)
    → 짧은 페이드 → 48kbps 모노 mp3. 길이 정보(Xing) 헤더는 남긴다."""
    limit = 10 ** (PEAK_DB / 20)
    t0, t1 = trim_points(src)
    af = (f'atrim={t0:.3f}:{t1:.3f},asetpts=PTS-STARTPTS,volume={gain:.2f}dB,'
          f'alimiter=limit={limit:.4f}:attack=3:release=60:level=disabled,'
          f'afade=t=in:d=0.008,afade=t=out:st={max(0.0, t1 - t0 - 0.04):.3f}:d=0.04')
    r = run(['ffmpeg', '-hide_banner', '-nostats', '-y', '-i', str(src), '-af', af, '-ac', '1', '-ar', '44100',
             '-c:a', 'libmp3lame', '-b:a', BITRATE, '-map_metadata', '-1', '-fflags', '+bitexact',
             '-flags:a', '+bitexact', '-id3v2_version', '0', str(dst)], text=True)
    if r.returncode: die(f'인코딩 실패 {Path(src).name}:\n' + r.stderr[-400:])


def cmd_encode(a):
    need_ffmpeg()
    sc_all = script()
    sc = [e for e in sc_all if e.get('ship')]
    miss = [e['key'] for e in sc if not (MASTERS / f"{e['key']}.mp3").is_file()]
    if miss: die(f'원본이 없는 대사 {len(miss)}줄: {miss[:5]} — fetch 가 먼저다')
    OUT.mkdir(parents=True, exist_ok=True)
    takes = load(TAKES) or {}
    by_who = {}
    for e in sc: by_who.setdefault(e['who'], []).append(e)
    total = 0
    for who, es in sorted(by_who.items()):
        gain, i, tp = speaker_gain(who, sc_all)
        for e in es:
            dst = OUT / f"{e['key']}.mp3"
            encode_one(MASTERS / f"{e['key']}.mp3", dst, gain)
            total += dst.stat().st_size
            takes.setdefault(e['key'], {})['asset'] = sha(dst)   # check 가 '이 파일이 이 원본의 인코딩인가'를 본다
        oi, otp = loud([OUT / f"{e['key']}.mp3" for e in es])
        print(f'{who:6} {len(es):2}줄  원본 {i:6.1f} LUFS / {tp:5.1f} dBTP  이득 {gain:+5.1f} dB  →  {oi:6.1f} LUFS / {otp:5.1f} dBTP')
    dump(TAKES, dict(sorted(takes.items())))
    print(f'{len(sc)}개 · {total / 1e6:.2f} MB · {BITRATE}bps 모노 → assets/voice/  (이어서 manifest → check)')
    return 0


# ---------------------------------------------------------------- fetch (표준 라이브러리만)
def api_key():
    k = os.environ.get('ELEVENLABS_API_KEY', '').strip()
    if not k: die('환경 변수 ELEVENLABS_API_KEY 가 필요하다 (키는 파일·로그에 남기지 않는다)')
    return k


def http(url, data, headers, timeout=180):
    req = urllib.request.Request(url, data=data, headers={**headers, 'xi-api-key': api_key()}, method='POST')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'replace')[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** (attempt + 1)); continue
            die(f'API {e.code}: {body}')
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 3: time.sleep(2 ** (attempt + 1)); continue
            die(f'API 연결 실패: {e}')


def tts(text, v, cast, seed):
    pr = params(v, cast)
    body = {'text': text, 'model_id': cast['model'], 'seed': seed,
            'voice_settings': {'stability': pr['stability'], 'similarity_boost': pr['similarity_boost']}}
    if pr['language_code']: body['language_code'] = pr['language_code']
    data, hdr = http(f"{API}/v1/text-to-speech/{v['voice_id']}?output_format={cast['output_format']}",
                     json.dumps(body, ensure_ascii=False).encode('utf-8'), {'Content-Type': 'application/json'})
    cost = next((int(x) for k, x in hdr.items() if k.lower() == 'character-cost'), None)
    return data, cost


def stt(path):
    """음성 → 텍스트 역검증. 합성음을 '들어' 볼 유일한 자동 수단이다."""
    bnd = uuid.uuid4().hex
    parts = b''
    for k, val in (('model_id', 'scribe_v2'), ('language_code', 'ko'), ('tag_audio_events', 'false')):
        parts += f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{val}\r\n'.encode()
    parts += (f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="a.mp3"\r\n'
              'Content-Type: audio/mpeg\r\n\r\n').encode() + Path(path).read_bytes() + f'\r\n--{bnd}--\r\n'.encode()
    data, _ = http(f'{API}/v1/speech-to-text', parts, {'Content-Type': f'multipart/form-data; boundary={bnd}'})
    return json.loads(data).get('text', '')


def norm(s):
    return re.sub(r'[^0-9A-Za-z가-힣]', '', re.sub(r'\[[^\]]*\]', '', s))


def score(heard, e):
    """받아쓴 문장이 낭독문·화면 표기 중 어느 쪽과든 얼마나 같은가 (숫자는 '60'/'육십' 어느 표기로도 받아써질 수 있다)."""
    h = norm(heard)
    return max(difflib.SequenceMatcher(None, h, norm(x)).ratio() for x in (e['tts'], plain(e['text'])))


# 받아쓰기는 소리를 글자로 '옮겨 적은 것'이라 일치도(score)만으로는 낱말 하나가 바뀐 것을 못 잡는다
# ('범인은'→'범위는'도 0.96 이다). 그래서 낱말 단위로 다시 본다 — 그리고 반드시 '탑재되는 형식'으로 본다:
# 원본(128kbps)에서 맞게 받아써지던 낱말이 인코딩본(48kbps)에서는 달리 받아써질 수 있다(실제로 있었다).
OFFS = (0, 10, 25, 50)                      # 시작 위치를 이만큼(ms) 밀어 가며 받아쓴다 — 경계선 발음은 여기서 뒤집힌다
SOUNDS = {'헤헤', '하', '타', '아', '어', '음'}   # 웃음·한숨·말 더듬 — 빠지거나 끼어도 낱말 차이로 치지 않는다


def lexical_diffs(e, heard):
    """받아쓴 문장이 낭독문과 '낱말이' 다른 곳 [(기대, 들림)]. 띄어쓰기·문장부호는 무시한다.
    숫자·영문 표기(60도, CO, 15cm)는 화면 표기에 그 순서로 있으면 정상, 아니면 차이로 친다.
    한계: 받아쓰기가 숫자를 한글로 적으면('일 년') 이 숫자 검사를 지나친다 — 그때는 낱말 비교가 본다.
    '열두 살'처럼 화면에 한글로 적힌 수를 '12살'로 받아쓰면 차이로 나오지만 틀린 것은 아니다."""
    exp, got = norm(e['tts']), norm(heard)
    num = r'[0-9]+(?:\.[0-9]+)?|[A-Za-z]+'
    shown = [x.lower() for x in re.findall(num, plain(e['text']))]
    out, at = [], 0
    for x in re.findall(num, heard):       # 화면 표기에 '그 순서로' 있어야 한다 — 1년/5년이 뒤바뀐 것도 잡는다
        if x.lower() in shown[at:]: at = shown.index(x.lower(), at) + 1
        else: out.append(('(화면 표기와 다른 숫자·영문)', x))
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, exp, got, autojunk=False).get_opcodes():
        x, y = exp[i1:i2], got[j1:j2]
        if op == 'equal' or re.search(r'[0-9A-Za-z]', y): continue          # 숫자·영문 표기 구간은 위에서 따로 봤다
        if (not y and x in SOUNDS) or (not x and y in SOUNDS): continue
        out.append((exp[max(0, i1 - 2):i2 + 2], got[max(0, j1 - 2):j2 + 2]))   # 앞뒤 두 글자씩 문맥을 붙인다
    return out


def hear(src, tmp, offs=OFFS):
    """파일을 시작 위치만 밀어 가며 받아쓴다 → {ms: 받아쓴 문장}"""
    out = {}
    for ms in offs:
        f = Path(tmp) / f'{Path(src).stem}_{ms}_{uuid.uuid4().hex[:6]}.flac'
        run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-af', f'adelay={ms}:all=1' if ms else 'anull',
             '-ac', '1', '-ar', '44100', '-c:a', 'flac', str(f)])
        out[ms] = stt(f); f.unlink()
    return out


def cmd_fetch(a):
    need_ffmpeg()
    import tempfile
    cast = load(CAST)
    if not cast: die(f'{CAST.relative_to(ROOT)} 가 없다')
    takes = load(TAKES) or {}
    sc_all = script()
    MASTERS.mkdir(parents=True, exist_ok=True)
    todo = [e for e in sc_all
            if (a.all or e.get('ship')) and (not a.who or e['who'] in a.who) and (not a.key or e['key'] in a.key)
            and (a.force or not (MASTERS / f"{e['key']}.mp3").is_file())]
    print(f'합성할 대사 {len(todo)}줄 · 낭독문 {sum(len(e["tts"]) for e in todo)}자')
    if a.dry_run:
        for e in todo: print(f"  {e['key']} {e['who']:5} {e['tts']}")
        return 0
    spent = 0
    tmpd = Path(tempfile.mkdtemp(prefix='bib-fetch-'))
    try:
        for n, e in enumerate(todo, 1):
            v = cast['voices'].get(e['who'])
            if not v: die(f"cast.json 에 화자가 없다: {e['who']}")
            prev = takes.get(e['key'], {})
            base = (prev.get('take', -1) + 1) if a.force else 0
            best = None
            for t in range(base, base + a.takes):
                seed = (int(e['key'], 16) + t * 7919) & 0xffffffff
                data, cost = tts(e['tts'], v, cast, seed); spent += cost or 0
                tmp = MASTERS / f".{e['key']}.take{t}.mp3"; tmp.write_bytes(data)
                d = duration(tmp)
                if a.no_verify:
                    heard, sc_, bad = '', 1.0, []
                else:
                    # 원본이 아니라 '탑재될 형식'으로 인코딩해, 시작 위치를 밀어 가며 받아쓴다.
                    enc = tmpd / f"{e['key']}.take{t}.mp3"
                    encode_one(tmp, enc, speaker_gain(e['who'], [x for x in sc_all if x['key'] != e['key']], extra=[tmp])[0])
                    hs = hear(enc, tmpd)
                    heard, sc_ = hs[0], min(score(h, e) for h in hs.values())
                    bad = sorted({f'{x}→{y}' for h in hs.values() for x, y in lexical_diffs(e, h)})
                cand = {'take': t, 'seed': seed, 'dur': round(d, 2), 'heard': heard, 'score': round(sc_, 3),
                        'diffs': bad, 'tmp': tmp}
                rank = lambda c: (-len(c['diffs']), c['score'])     # 낱말 차이가 적은 것, 그다음 일치도
                if best is None or rank(cand) > rank(best):
                    if best: best['tmp'].unlink()
                    best = cand
                else: tmp.unlink()
                if d > 0.6 and sc_ >= a.accept and not bad: break
            best.pop('tmp').replace(MASTERS / f"{e['key']}.mp3")
            takes[e['key']] = {'who': e['who'], 'voice_id': v['voice_id'], 'model': cast['model'], 'params': params(v, cast),
                               'tts': e['tts'], 'sha256': sha(MASTERS / f"{e['key']}.mp3"), **best}   # 옛 인코딩 기록(asset)은 버린다
            dump(TAKES, dict(sorted(takes.items())))
            flag = '' if best['score'] >= a.accept and not best['diffs'] else '   ← 확인 필요'
            print(f"[{n}/{len(todo)}] {e['key']} {e['who']:5} take {best['take']} {best['dur']:5.2f}s 일치 {best['score']:.2f}{flag}")
            if flag: print(f"      낭독문  {e['tts']}\n      받아씀  {best['heard']}\n      낱말 차이  {best['diffs']}")
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    print(f'완료 — 크레딧 {spent} 사용 (이어서 encode → manifest → check)')
    return 0


def cmd_probe(a):
    """탑재 파일(assets/voice)을 시작 위치만 0·10·25·50ms 밀어 가며 받아써, 낭독문과 '낱말이' 다르게 받아써진
    곳을 보여 주고 takes.json 의 probe 에 적는다. 받아쓰기는 귀가 아니다 — 같은 소리를 다른 철자로 적기도 한다
    (설래원/설레원, 삼발이/삼바리). 여기 나온 줄은 '들어 볼 줄'의 목록이지 오류의 목록이 아니다.
    정말 달리 들리는 줄은 fetch --force --key <키> 로 다시 뽑는다(fetch 도 같은 방식으로 테이크를 고른다)."""
    need_ffmpeg()
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    sc = {e['key']: e for e in script()}
    keys = a.key or sorted(p.stem for p in OUT.glob('*.mp3'))
    miss = [k for k in keys if k not in sc or not (OUT / f'{k}.mp3').is_file()]
    if miss: die(f'탑재 파일이나 대본이 없는 키: {miss[:5]}')
    takes = load(TAKES) or {}
    tmpd = Path(tempfile.mkdtemp(prefix='bib-probe-'))
    try:
        with ThreadPoolExecutor(4) as ex:
            heard = dict(zip(keys, ex.map(lambda k: hear(OUT / f'{k}.mp3', tmpd), keys)))
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    n = 0
    for k in keys:
        where = {}
        for ms, h in heard[k].items():
            for x, y in lexical_diffs(sc[k], h): where.setdefault(f'{x}→{y}', []).append(ms)
        takes.setdefault(k, {})['probe'] = {'asset': sha(OUT / f'{k}.mp3'), 'diffs': {d: ms for d, ms in sorted(where.items())}}
        if where:
            n += 1
            print(f"{k} {sc[k]['who']}  " + ' · '.join(f"{d} (+{'/'.join(map(str, ms))}ms)" for d, ms in sorted(where.items())))
    dump(TAKES, dict(sorted(takes.items())))
    print(f'{len(keys)}개 파일 중 {n}개에서 낭독문과 다르게 받아써진 낱말이 있다 — 들어 보고, 정말 다르면 다시 뽑는다.')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check', help='정합성 검사'); c.set_defaults(fn=cmd_check)
    c.add_argument('--allow-unvoiced', action='store_true', help='음성 없는 대사를 실패가 아니라 주의로 다룬다')
    sub.add_parser('encode', help='원본 → assets/voice').set_defaults(fn=cmd_encode)
    sub.add_parser('manifest', help='VOICE_HAVE 갱신').set_defaults(fn=cmd_manifest)
    sub.add_parser('prune', help='탑재 대상을 지금 대사에 맞춘다(내림·되살림)').set_defaults(fn=cmd_prune)
    f = sub.add_parser('fetch', help='ElevenLabs 로 원본 합성'); f.set_defaults(fn=cmd_fetch)
    f.add_argument('--all', action='store_true', help='ship:false(보험용) 대사까지')
    f.add_argument('--who', nargs='*', help='이 화자만')
    f.add_argument('--key', nargs='*', help='이 키만')
    f.add_argument('--force', action='store_true', help='원본이 있어도 새 테이크로 다시 합성')
    f.add_argument('--takes', type=int, default=3, help='역검증이 깨끗하지 않을 때(일치도 미달·낱말 차이) 최대 시도 횟수')
    f.add_argument('--accept', type=float, default=0.86, help='역검증 일치도 합격선')
    f.add_argument('--no-verify', action='store_true', help='음성→텍스트 역검증 생략')
    f.add_argument('--dry-run', action='store_true', help='무엇을 합성할지만 보여 준다')
    pb = sub.add_parser('probe', help='탑재 파일을 받아써 낭독문과 다르게 들리는 낱말 찾기'); pb.set_defaults(fn=cmd_probe)
    pb.add_argument('--key', nargs='*', help='이 키만 (기본: 탑재 파일 전부)')
    a = ap.parse_args()
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())

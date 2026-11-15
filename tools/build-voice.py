#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대사 음성 도구 — tools/voice/(대본·배역·원본) → assets/voice/*.mp3 + index.html 의 VOICE_HAVE

게임은 실행 중에 어떤 API 도 부르지 않는다. 음성은 ElevenLabs TTS 로 '한 번' 합성해
파일로 커밋해 둔 것이고, 이 도구가 그 합성·검수·인코딩·정합성 검사를 맡는다.

  python3 tools/build-voice.py check      # 정합성 검사 (API 키 불필요, 커밋 전 필수)
  python3 tools/build-voice.py encode     # 원본 → assets/voice/*.mp3 (API 키 불필요, 반복 가능)
  python3 tools/build-voice.py manifest   # index.html 의 VOICE_HAVE 한 줄 갱신
  python3 tools/build-voice.py prune      # 대사가 바뀌어 주인이 없어진 assets/voice 파일 삭제
  python3 tools/build-voice.py fetch      # 원본 합성 (ELEVENLABS_API_KEY 필요, 표준 라이브러리만 사용)

파일
  tools/voice/script.json   대사별 {key, who, src, text(화면 표기), tts(낭독문), ship}
                            tts 는 숫자·단위를 한글로 풀고(60℃→육십 도) 지문은 연기 태그로 바꾼 것.
                            ship:false 는 게임에 싣지 않는 보험용 원본(단서 설명·탐정의 질문).
  tools/voice/cast.json     화자 → ElevenLabs 목소리·모델·설정
  tools/voice/masters/      API 가 준 원본 mp3 (재인코딩의 출발점 — API 키가 없어도 음량·비트레이트를 다시 맞출 수 있다)
  tools/voice/takes.json    합성 기록(시드·길이·음성→텍스트 역검증 결과)

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
      add(ck+'.CLUES.'+k+'.desc', '단서', c.desc, false);
      if(c.fast) add(ck+'.CLUES.'+k+'.fast', '단서', c.fast, false); }
  } return out; })()"""


def chrome():
    for p in (os.environ.get('BIB_CHROME'), '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', '/opt/pw-browsers/chromium'):
        if p and os.path.exists(p): return p
    return None   # playwright 가 스스로 찾게 둔다


def page_lines():
    """index.html 을 헤드리스 크롬으로 열어 대사를 열거한다 (file:// — 서버 불필요).
    spoken=True 는 '말하는 사람이 있는 대사'(게임에 싣는 범위), False 는 단서 설명·탐정의 질문."""
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
    for e in sc:
        if e['who'] not in cast.get('voices', {}): bad.append(f"cast.json 에 화자가 없다: {e['who']}")
        if not e.get('tts', '').strip(): bad.append(f"낭독문(tts)이 비었다: {e['key']}")
    unvoiced = [l for k, l in spoken.items() if k not in files]
    for l in unvoiced:
        (warn if a.allow_unvoiced else bad).append(
            f"음성 없는 대사: {l['src']} ({l['who']}: {plain(l['text'])[:28]}…)")

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
    spoken = {l['key'] for l in page_lines() if l['spoken']}
    ship = {e['key'] for e in script() if e.get('ship')}
    gone = [p for p in sorted(OUT.glob('*.mp3')) if p.stem not in spoken or p.stem not in ship]
    for p in gone:
        print('삭제  ' + str(p.relative_to(ROOT))); p.unlink()
    print(f'{len(gone)}개 삭제 — 원본(tools/voice/masters)은 남겨 둔다. 이어서 manifest 를 돌린다.')
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


def cmd_encode(a):
    need_ffmpeg()
    sc = [e for e in script() if e.get('ship')]
    miss = [e['key'] for e in sc if not (MASTERS / f"{e['key']}.mp3").is_file()]
    if miss: die(f'원본이 없는 대사 {len(miss)}줄: {miss[:5]} — fetch 가 먼저다')
    OUT.mkdir(parents=True, exist_ok=True)
    by_who = {}
    for e in sc: by_who.setdefault(e['who'], []).append(e)
    total = 0
    for who, es in sorted(by_who.items()):
        srcs = [MASTERS / f"{e['key']}.mp3" for e in es]
        i, tp = loud(srcs)
        gain = TARGET_I - i
        # 화자 단위 고정 이득 — 줄마다 정규화하면 속삭임과 외침이 같은 크기가 되어 연기가 눌린다.
        # 이득 뒤 피크가 상한을 넘는 화자만 리미터가 봉우리를 눌러 준다.
        limit = 10 ** (PEAK_DB / 20)
        for e, src in zip(es, srcs):
            t0, t1 = trim_points(src)
            af = (f'atrim={t0:.3f}:{t1:.3f},asetpts=PTS-STARTPTS,volume={gain:.2f}dB,'
                  f'alimiter=limit={limit:.4f}:attack=3:release=60:level=disabled,'
                  f'afade=t=in:d=0.008,afade=t=out:st={max(0.0, t1 - t0 - 0.04):.3f}:d=0.04')
            dst = OUT / f"{e['key']}.mp3"
            r = run(['ffmpeg', '-hide_banner', '-nostats', '-y', '-i', str(src), '-af', af, '-ac', '1', '-ar', '44100',
                     '-c:a', 'libmp3lame', '-b:a', BITRATE, '-map_metadata', '-1', '-fflags', '+bitexact',
                     '-flags:a', '+bitexact', '-id3v2_version', '0', '-write_xing', '0', str(dst)], text=True)
            if r.returncode: die(f'인코딩 실패 {src.name}:\n' + r.stderr[-400:])
            total += dst.stat().st_size
        oi, otp = loud([OUT / f"{e['key']}.mp3" for e in es])
        print(f'{who:6} {len(es):2}줄  원본 {i:6.1f} LUFS / {tp:5.1f} dBTP  이득 {gain:+5.1f} dB  →  {oi:6.1f} LUFS / {otp:5.1f} dBTP')
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
    body = {'text': text, 'model_id': cast['model'], 'seed': seed,
            'voice_settings': {'stability': v.get('stability', 0.5), 'similarity_boost': v.get('similarity_boost', 0.75)}}
    if cast.get('language_code'): body['language_code'] = cast['language_code']
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


def cmd_fetch(a):
    need_ffmpeg()
    cast = load(CAST)
    if not cast: die(f'{CAST.relative_to(ROOT)} 가 없다')
    takes = load(TAKES) or {}
    MASTERS.mkdir(parents=True, exist_ok=True)
    todo = [e for e in script()
            if (a.all or e.get('ship')) and (not a.who or e['who'] in a.who) and (not a.key or e['key'] in a.key)
            and (a.force or not (MASTERS / f"{e['key']}.mp3").is_file())]
    print(f'합성할 대사 {len(todo)}줄 · 낭독문 {sum(len(e["tts"]) for e in todo)}자')
    if a.dry_run:
        for e in todo: print(f"  {e['key']} {e['who']:5} {e['tts']}")
        return 0
    spent = 0
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
            heard = '' if a.no_verify else stt(tmp)
            sc_ = 1.0 if a.no_verify else score(heard, e)
            cand = {'take': t, 'seed': seed, 'dur': round(d, 2), 'heard': heard, 'score': round(sc_, 3), 'tmp': tmp}
            if best is None or cand['score'] > best['score']:
                if best: best['tmp'].unlink()
                best = cand
            else: tmp.unlink()
            if d > 0.6 and sc_ >= a.accept: break
        best.pop('tmp').replace(MASTERS / f"{e['key']}.mp3")
        takes[e['key']] = {'who': e['who'], 'voice_id': v['voice_id'], 'model': cast['model'], 'tts': e['tts'],
                           'sha256': hashlib.sha256((MASTERS / f"{e['key']}.mp3").read_bytes()).hexdigest()[:16], **best}
        dump(TAKES, dict(sorted(takes.items())))
        flag = '' if best['score'] >= a.accept else '   ← 확인 필요'
        print(f"[{n}/{len(todo)}] {e['key']} {e['who']:5} take {best['take']} {best['dur']:5.2f}s 일치 {best['score']:.2f}{flag}")
        if flag: print(f"      낭독문  {e['tts']}\n      받아씀  {best['heard']}")
    print(f'완료 — 크레딧 {spent} 사용 (이어서 encode → manifest → check)')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check', help='정합성 검사'); c.set_defaults(fn=cmd_check)
    c.add_argument('--allow-unvoiced', action='store_true', help='음성 없는 대사를 실패가 아니라 주의로 다룬다')
    sub.add_parser('encode', help='원본 → assets/voice').set_defaults(fn=cmd_encode)
    sub.add_parser('manifest', help='VOICE_HAVE 갱신').set_defaults(fn=cmd_manifest)
    sub.add_parser('prune', help='주인 없는 assets/voice 파일 삭제').set_defaults(fn=cmd_prune)
    f = sub.add_parser('fetch', help='ElevenLabs 로 원본 합성'); f.set_defaults(fn=cmd_fetch)
    f.add_argument('--all', action='store_true', help='ship:false(보험용) 대사까지')
    f.add_argument('--who', nargs='*', help='이 화자만')
    f.add_argument('--key', nargs='*', help='이 키만')
    f.add_argument('--force', action='store_true', help='원본이 있어도 새 테이크로 다시 합성')
    f.add_argument('--takes', type=int, default=3, help='역검증이 기준에 못 미칠 때 최대 시도 횟수')
    f.add_argument('--accept', type=float, default=0.86, help='역검증 일치도 합격선')
    f.add_argument('--no-verify', action='store_true', help='음성→텍스트 역검증 생략')
    f.add_argument('--dry-run', action='store_true', help='무엇을 합성할지만 보여 준다')
    a = ap.parse_args()
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())

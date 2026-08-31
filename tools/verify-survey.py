# -*- coding: utf-8 -*-
"""survey.html 검증 스위트 (V1~V11).

실행 전제: pip install playwright fonttools brotli (Pillow 불필요),
Chromium 은 /opt/pw-browsers/chromium-1194/chrome-linux/chrome,
로컬 서버 python3 -m http.server 8899 (저장소 루트에서).

핵심 회귀 가드(V7): survey.html 은 게임의 서브셋 폰트를 재사용하므로,
화면에 렌더되는 모든 비ASCII 글자가 해당 서브셋 cmap 에 있어야 한다.
문구를 고쳤다가 이 검사가 실패하면 — 그 글자를 피해서 다시 쓰거나
tools/build-fonts.sh 를 survey.html 까지 자르도록 확장해야 한다.
"""
import os, re, sys
from playwright.sync_api import sync_playwright
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
URL = "http://localhost:8899/survey.html"
SHOTS = os.path.join(ROOT, "tools", "survey_shots")
os.makedirs(SHOTS, exist_ok=True)

fails = []
def chk(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL") + " " + name + ((" — " + str(detail)[:220]) if (detail and not cond) else ""))
    if not cond: fails.append(name)

COLLECT_JS = """() => {
  const out=[];
  const walk=el=>{
    for(const n of el.childNodes){
      if(n.nodeType===3){
        const fam=getComputedStyle(el).fontFamily;
        for(const ch of n.textContent) if(ch.codePointAt(0)>127) out.push([ch,fam]);
      } else if(n.nodeType===1){
        const st=getComputedStyle(n);
        if(st.display!=='none' && st.visibility!=='hidden') walk(n);
      }
    }
  };
  walk(document.body);
  return out;
}"""

LEAK_WORDS = ["정답", "점수", "채점", "맞았", "맞힌", "틀렸", "틀린", "해설", "/5", "+1", "+2", "+3", "+4", "+5", "O X"]

def visible_text(pg):
    return pg.evaluate("document.body.innerText")

def fill_quiz(pg, answers, fun=None, rec=None, memo=None, sid="10132", name="한세인"):
    pg.fill("#inId", sid); pg.fill("#inName", name)
    for i, v in enumerate(answers):
        pg.check(f"input[name=q{i}][value='{v}']")
    if fun is not None: pg.check(f"input[name=scFun][value='{fun}']")
    if rec is not None: pg.check(f"input[name=scRec][value='{rec}']")
    if memo is not None: pg.fill("#inMemo", memo)

def main():
    # cmap 로드
    my = TTFont(os.path.join(ROOT, "assets/fonts/NanumMyeongjo-800.subset.woff2")).getBestCmap()
    no = TTFont(os.path.join(ROOT, "assets/fonts/NotoSansKR-400.subset.woff2")).getBestCmap()
    chars_seen = []   # (ch, family)

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin="http://localhost:8899")
        pg = ctx.new_page()
        errs, ext = [], []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("request", lambda r: ext.append(r.url) if not r.url.startswith("http://localhost:8899") else None)
        pg.goto(URL); pg.wait_for_timeout(900)
        chars_seen += pg.evaluate(COLLECT_JS)
        pg.screenshot(path=os.path.join(SHOTS, "01_landing.png"), full_page=True)

        # ---------- V1 사전 무유출 ----------
        print("[V1 사전 무유출]")
        pg.click("a[href='#pre']"); pg.wait_for_timeout(400)
        chars_seen += pg.evaluate(COLLECT_JS)
        pg.screenshot(path=os.path.join(SHOTS, "02_pre_form.png"), full_page=True)
        fill_quiz(pg, [2, 1, 3, 4, 3])          # 3개 정답 (Q2·Q4 오답)
        pg.click("#submitBtn"); pg.wait_for_timeout(400)
        chk("사전 완료 화면 도달", pg.evaluate("!document.getElementById('view-pre-done').hidden"))
        txt = visible_text(pg)
        leak = [w for w in LEAK_WORDS if w in txt]
        chk("점수·정오 어휘 부재", not leak, leak)
        chk("정오 클래스 DOM 부재", pg.evaluate("document.querySelectorAll('.good,.bad,.r-item').length") == 0)
        saved = pg.evaluate("JSON.parse(localStorage.getItem('hansein.survey.v1'))")
        chk("사전 답 저장(1-indexed)", saved and saved.get("pre", {}).get("a") == [2, 1, 3, 4, 3], saved)
        chk("게임 키와 충돌 없음", pg.evaluate("localStorage.getItem('hansein.fast')") in (None, "0", "1"))
        chars_seen += pg.evaluate(COLLECT_JS)
        pg.screenshot(path=os.path.join(SHOTS, "03_pre_done.png"), full_page=True)
        # 기록이 있는 랜딩 상태도 커버리지 수집 대상에 넣는다
        pg.click("#view-pre-done a[href='#']"); pg.wait_for_timeout(300)
        chars_seen += pg.evaluate(COLLECT_JS)

        # ---------- V2+V3 사후 채점·델타 ----------
        print("[V2·V3 사후 채점·델타]")
        pg.goto(URL + "#post"); pg.wait_for_timeout(400)
        chk("해시 직진입(#post)", pg.evaluate("!document.getElementById('view-form').hidden"))
        chk("사전 학번 프리필", pg.evaluate("document.getElementById('inId').value") == "10132")
        chars_seen += pg.evaluate(COLLECT_JS)
        # 미응답 차단 확인
        pg.click("#submitBtn"); pg.wait_for_timeout(300)
        chk("미응답 제출 차단", pg.evaluate("!document.getElementById('view-form').hidden")
            and pg.evaluate("document.querySelectorAll('#qList fieldset.miss').length") == 1)
        chars_seen += pg.evaluate(COLLECT_JS)   # 미응답 토스트 표시 중
        fill_quiz(pg, [2, 3, 3, 4, 3], fun=4, rec=5, memo="부탄캔은 3년까지")   # 4개 정답
        pg.screenshot(path=os.path.join(SHOTS, "04_post_form.png"), full_page=True)
        pg.click("#submitBtn"); pg.wait_for_timeout(500)
        chk("결과 화면 도달", pg.evaluate("!document.getElementById('view-post-result').hidden"))
        chk("점수 4", pg.evaluate("document.getElementById('scoreN').textContent") == "4")
        chip = pg.evaluate("document.getElementById('deltaChip').innerText")
        chk("델타 3/5 → 4/5 (+1)", "3/5" in chip and "4/5" in chip and "+1" in chip, chip)
        marks = pg.evaluate("[...document.querySelectorAll('.r-item .r-mark')].map(e=>e.textContent)")
        chk("문항별 정오 OOOXO", marks == ["O", "O", "O", "X", "O"], marks)
        wrong_line = pg.evaluate("document.querySelector('.r-item.bad .r-line').textContent")
        chk("오답에 정답 병기", "정답 3번" in wrong_line, wrong_line)
        txt = visible_text(pg)
        chk("해설·근거 노출", "사고 재현 단계" in txt and "트럭 짐칸" in txt)
        sum_txt = pg.evaluate("document.getElementById('sumText').value")
        ok_sum = re.search(r"^\[터지기 전에\] 한세인\(10132\) \| 사전 3/5 → 사후 4/5 \(\+1\) \| OXOXO→OOOXO \| 재미 4 · 추천 5 \| 기억: 부탄캔은 3년까지$", sum_txt)
        chk("요약 문자열 포맷", bool(ok_sum), sum_txt)
        chars_seen += pg.evaluate(COLLECT_JS)
        pg.screenshot(path=os.path.join(SHOTS, "05_post_result.png"), full_page=True)

        # ---------- V4 복사 ----------
        print("[V4 복사]")
        pg.click("#copyBtn"); pg.wait_for_timeout(300)
        clip = pg.evaluate("navigator.clipboard.readText()")
        chk("클립보드 내용 일치", clip == sum_txt)
        chk("복사 토스트", "복사" in pg.evaluate("document.getElementById('toast').textContent"))
        chars_seen += pg.evaluate(COLLECT_JS)   # 복사 토스트 표시 중

        # ---------- V5 모바일 레이아웃 ----------
        print("[V5 모바일 390px]")
        chk("가로 스크롤 없음", pg.evaluate("document.documentElement.scrollWidth") <= 390)
        h = pg.evaluate("Math.min(...[...document.querySelectorAll('#view-post-result .btn')].map(e=>e.getBoundingClientRect().height))")
        chk("버튼 터치 타깃 44px+", h >= 44, h)

        # ---------- V11 리셋 ----------
        print("[V11 리셋]")
        pg.click("#view-post-result .btn.ghost"); pg.wait_for_timeout(300)
        chk("리셋 후 랜딩", pg.evaluate("!document.getElementById('view-landing').hidden"))
        chk("키 삭제", pg.evaluate("localStorage.getItem('hansein.survey.v1')") is None)
        chars_seen += pg.evaluate(COLLECT_JS)   # 리셋 토스트 표시 중

        # ---------- V3b 사전 없이 사후 ----------
        pg.goto(URL + "#post"); pg.wait_for_timeout(400)
        fill_quiz(pg, [2, 3, 3, 3, 3], fun=5, rec=5)
        pg.click("#submitBtn"); pg.wait_for_timeout(400)
        chk("사전 없음 표기", "사전 기록 없음" in pg.evaluate("document.getElementById('deltaChip').textContent"))
        chk("5/5 만점", pg.evaluate("document.getElementById('scoreN').textContent") == "5")
        chars_seen += pg.evaluate(COLLECT_JS)

        # ---------- V6 위생 ----------
        print("[V6 위생]")
        chk("콘솔 에러 0건", len(errs) == 0, errs)
        chk("외부 요청 0건", len(ext) == 0, ext)
        fonts_ok = pg.evaluate("""(async () => {
          const fs=['800 20px "Nanum Myeongjo"','400 16px "Noto Sans KR"','700 16px "Noto Sans KR"'];
          for(const f of fs){ const r=await document.fonts.load(f); if(!r.length||!document.fonts.check(f)) return f; }
          return true; })()""")
        chk("서브셋 3면 로드", fonts_ok is True, fonts_ok)

        # ---------- V8 키보드 ----------
        print("[V8 키보드]")
        pg2 = ctx.new_page()
        pg2.goto(URL + "#pre"); pg2.wait_for_timeout(400)
        pg2.fill("#inId", "20101"); pg2.fill("#inName", "테스트")
        for i in range(5):
            pg2.focus(f"input[name=q{i}][value='1']")
            pg2.keyboard.press("ArrowDown")     # 1 → 2번 선택
        picked = pg2.evaluate("[0,1,2,3,4].map(i=>{const e=document.querySelector(`input[name=q${i}]:checked`);return e&&e.value})")
        chk("화살표 키 선택", picked == ["2"] * 5, picked)
        pg2.focus("#submitBtn"); pg2.keyboard.press("Enter"); pg2.wait_for_timeout(400)
        chk("Enter 제출 → 완료 화면", pg2.evaluate("!document.getElementById('view-pre-done').hidden"))
        pg2.close()

        # ---------- V10 저장 불가 환경 ----------
        print("[V10 저장 불가]")
        ctx3 = b.new_context(viewport={"width": 390, "height": 844})
        pg3 = ctx3.new_page()
        pg3.add_init_script("""Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}});""")
        errs3 = []
        pg3.on("pageerror", lambda e: errs3.append(str(e)))
        pg3.goto(URL + "#pre"); pg3.wait_for_timeout(400)
        pg3.fill("#inId", "1"); pg3.fill("#inName", "가")
        for i in range(5):
            pg3.check(f"input[name=q{i}][value='2']")
        pg3.click("#submitBtn"); pg3.wait_for_timeout(400)
        chk("차단 환경 사전 완료 + 경고", pg3.evaluate("!document.getElementById('view-pre-done').hidden")
            and pg3.evaluate("!document.getElementById('preSaveWarn').hidden"))
        chars_seen += pg3.evaluate(COLLECT_JS)   # 저장 경고 문구 상태
        pg3.goto(URL + "#post"); pg3.wait_for_timeout(400)
        ans_v10 = [2, 3, 3, 3, 3]
        for i in range(5):
            pg3.check("input[name=q%d][value='%d']" % (i, ans_v10[i]))
        pg3.check("input[name=scFun][value='3']"); pg3.check("input[name=scRec][value='3']")
        pg3.click("#submitBtn"); pg3.wait_for_timeout(400)
        chk("차단 환경 사후 채점", pg3.evaluate("document.getElementById('scoreN').textContent") == "5")
        chk("차단 환경 pageerror 0", not errs3, errs3)
        ctx3.close()

        # ---------- V4b 클립보드 미지원 폴백 ----------
        print("[V4b 클립보드 폴백]")
        ctx4 = b.new_context(viewport={"width": 390, "height": 844})
        pg4 = ctx4.new_page()
        pg4.add_init_script("Object.defineProperty(navigator,'clipboard',{value:undefined});")
        pg4.goto(URL + "#post"); pg4.wait_for_timeout(400)
        for i in range(5):
            pg4.check(f"input[name=q{i}][value='2']")
        pg4.check("input[name=scFun][value='4']"); pg4.check("input[name=scRec][value='4']")
        pg4.click("#submitBtn"); pg4.wait_for_timeout(400)
        pg4.click("#copyBtn"); pg4.wait_for_timeout(300)
        chk("폴백에서도 토스트·무예외", "복사" in pg4.evaluate("document.getElementById('toast').textContent"))
        chars_seen += pg4.evaluate(COLLECT_JS)   # 폴백 안내 토스트 상태
        ctx4.close()

        # ---------- V9 file:// 스모크 ----------
        print("[V9 file://]")
        ctx5 = b.new_context(viewport={"width": 390, "height": 844})
        pg5 = ctx5.new_page()
        errs5 = []
        pg5.on("pageerror", lambda e: errs5.append(str(e)))
        pg5.goto("file://" + os.path.join(ROOT, "survey.html") + "#pre"); pg5.wait_for_timeout(600)
        chk("file:// 폼 렌더", pg5.evaluate("document.querySelectorAll('#qList fieldset').length") == 5)
        f_ok = pg5.evaluate("""(async () => {
          const r=await document.fonts.load('800 20px "Nanum Myeongjo"'); return r.length>0; })()""")
        chk("file:// 폰트 로드", f_ok is True)
        chk("file:// 게임 링크 상대경로", pg5.evaluate("document.querySelector('#view-landing a[href=\\'index.html\\']')!==null"))
        chk("file:// pageerror 0", not errs5, errs5)
        ctx5.close()
        b.close()

    # ---------- V7 폰트 커버리지 (cmap 대조) ----------
    print("[V7 서브셋 커버리지]")
    bad = set()
    for ch, fam in chars_seen:
        cp = ord(ch)
        if fam.split(",")[0].strip('"\' ').startswith("Nanum"):
            if cp not in my: bad.add((ch, "명조"))
        elif "Noto Sans KR" in fam.split(",")[0]:
            if cp not in no: bad.add((ch, "Noto"))
        # 시스템 스택(입력 에코·복사 상자)은 검사 제외
    chk("렌더 글자 전부 서브셋에 존재", not bad, sorted(bad))

    print()
    print("PASS — survey.html 검증 전부 통과" if not fails else "FAIL: " + ", ".join(fails))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())

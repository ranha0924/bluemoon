#!/usr/bin/env bash
# assets/fonts/*.subset.woff2 재생성 스크립트.
#
# 언제 돌리나: index.html 의 시나리오·UI 텍스트에 "새 글자"를 추가했을 때.
# 서브셋은 index.html 에 실제로 등장하는 문자 + ASCII(U+0020-007E)만 담으므로,
# 안 돌리면 새 글자만 시스템 폰트로 폴백되어 명조/고딕이 섞여 보인다.
#
# 필요: python3 + `pip install fonttools brotli`
# 원본: Google Fonts 가 배포하는 나눔명조 700/800, Noto Sans KR 400/700 (SIL OFL 1.1).
#       아주 오래된 User-Agent 로 css2 API 를 부르면 unicode-range 분할 없는
#       전체 TTF 한 벌을 내려 주므로 그것을 받아 자른다.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'EOF'
import re, ssl, urllib.request, os
from fontTools.subset import main as subset_main

UA = "Wget/1.20.3 (linux-gnu)"          # 구형 UA → 분할 없는 전체 TTF 응답
CSS = ("https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@700;800"
       "&family=Noto+Sans+KR:wght@400;700&display=swap")
OUT = {  # css2 응답의 (family, weight) → 저장 파일명
    ("Nanum Myeongjo", "700"): "NanumMyeongjo-700.subset.woff2",
    ("Nanum Myeongjo", "800"): "NanumMyeongjo-800.subset.woff2",
    ("Noto Sans KR", "400"): "NotoSansKR-400.subset.woff2",
    ("Noto Sans KR", "700"): "NotoSansKR-700.subset.woff2",
}
ctx = ssl.create_default_context()
ca = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
if os.path.exists(ca):
    ctx = ssl.create_default_context(cafile=ca)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return r.read()

css = get(CSS).decode()
blocks = re.findall(r"@font-face\s*\{([^}]+)\}", css)
for blk in blocks:
    fam = re.search(r"font-family:\s*'([^']+)'", blk).group(1)
    wgt = re.search(r"font-weight:\s*(\d+)", blk).group(1)
    url = re.search(r"src:\s*url\((\S+?)\)", blk).group(1)
    out = OUT.get((fam, wgt))
    if not out:
        continue
    raw = f"/tmp/font_{fam.replace(' ', '')}_{wgt}.ttf"
    open(raw, "wb").write(get(url))
    subset_main([raw, "--text-file=index.html", "--unicodes=U+0020-007E",
                 f"--output-file=assets/fonts/{out}", "--flavor=woff2",
                 "--name-IDs=0,1,2,3,4,6,13,14", "--layout-features=*"])
    print(out, os.path.getsize(f"assets/fonts/{out}") // 1024, "KB")
print("done — 브라우저에서 열어 명조/고딕이 섞이지 않는지 확인할 것")
EOF

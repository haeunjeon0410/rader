"""한국 해커톤류 수집기: 위비티 + 링커리어 -> data/hackathons.json (표준 라이브러리만 사용)

'해커톤류'는 이름에 해커톤이 없어도 포함한다: ~톤(아이디어톤·데이터톤·키로톤…), 게임잼/Jam,
바이브코딩, 코딩·개발 대회. 앞의 것들은 kind=core, 개발 경진대회류는 kind=loose.
"""
import json, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

from details import linkareer_detail, wevity_detail

KST = timezone(timedelta(hours=9))
DATA = Path(__file__).parent / "data" / "hackathons.json"
SEARCH_TERMS = ["해커톤", "hackathon", "톤", "잼", "jam", "바이브코딩", "코딩", "앱 개발", "SW 경진", "게임 개발", "AI 개발"]
# 이 단어로 검색해서 나온 건 제목이 평범해도 후보로 올리고, 본문을 읽어 해커톤류인지 확인한다
BODY_TERMS = {"해커톤", "hackathon", "잼", "jam", "바이브코딩", "코딩"}
SEARCH_PAGES = 2
CATEGORY_PAGES = 3

CORE = re.compile(
    r"해커\s?톤|hackathon|[A-Za-z]{2,}thon\b|[가-힣A-Za-z0-9]{2,}톤(?![가-힣A-Za-z])"
    r"|잼(?![가-힣A-Za-z])|\bjam\b|game\s?jam|바이브\s?코딩|vibe\s?coding"
    r"|(?:AI|인공지능)\s?.{0,4}게임\s?(?:개발|제작|·|콘텐츠)|게임\s?(?:개발|제작)\s?.{0,4}(?:AI|인공지능)",
    re.I,
)
LOOSE = re.compile(
    r"(코딩|개발|SW|소프트웨어|앱|프로그래밍)\s?(경진|챌린지|대회|공모|콘테스트|챔피언십)|코딩\s?테스트|프로그래밍"
    r"|게임.{0,10}(개발|제작|콘텐츠).{0,10}(공모|대회|경진|챌린지)|AI.{0,8}(게임|콘텐츠|서비스|앱).{0,10}(공모|대회|경진)",
    re.I,
)


def final_kind(kind, extra):
    """제목으로 정한 kind를 본문 신호로 보정: 본문이 해커톤·바이브코딩·잼 성격이면 core로 올린다. None이면 탈락."""
    n = extra.get("hack_mentions") or 0
    if kind is None:
        return "core" if n >= 2 else None
    if kind == "loose" and n >= 1:
        return "core"
    return kind
# '톤'으로 끝나지만 해커톤이 아닌 것
NOT_HACK = re.compile(r"마라톤|트라이애슬론|철인|워싱톤|뉴톤|런닝톤|걷기|달리기|marathon", re.I)


def kind_of(title):
    if NOT_HACK.search(title):
        return None
    if CORE.search(title):
        return "core"
    if LOOSE.search(title):
        return "loose"
    return None


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (hackathon-radar)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def wevity_list(url, today):
    """위비티 목록 페이지 -> [(ix, 제목, 주최, 마감일)] (마감 지난 건 제외)"""
    rows = []
    for li in re.findall(r"<li\s*[^>]*>(.*?)</li>", get(url), re.S):
        m = re.search(r'<div class="tit">\s*<a href="[^"]*?ix=(\d+)">(.*?)(?:<span|</a>)', li, re.S)
        if not m or re.search(r"D\+\d+", li):  # D+N = 이미 마감
            continue
        title = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        organ = re.search(r'<div class="organ">(.*?)</div>', li, re.S)
        d = re.search(r"D-(\d+)|D-Day", li)
        deadline = (today + timedelta(days=int(d.group(1)) if d.group(1) else 0)).isoformat() if d else None
        rows.append((m.group(1), title, unescape(organ.group(1)).strip() if organ else "", deadline))
    return rows


def wevity(today):
    urls = [  # (주소, 제목이 평범해도 후보로 올릴지)
        (f"https://www.wevity.com/?c=find&s=1&sp=contents&sw={urllib.parse.quote(t)}&gp={p}", t in BODY_TERMS)
        for t in SEARCH_TERMS for p in range(1, SEARCH_PAGES + 1)
    ] + [
        (f"https://www.wevity.com/?c=find&s=1&gub=1&cidx={c}&gp={p}", False)
        for c in (20, 21, 22) for p in range(1, CATEGORY_PAGES + 1)  # 웹/IT · 게임/SW · 과학/공학
    ]
    cand, fails = {}, 0
    for u, body_ok in urls:
        try:
            for ix, title, host, deadline in wevity_list(u, today):
                kind = kind_of(title)
                if (kind or body_ok) and not (ix in cand and cand[ix][3] and not kind):
                    cand[ix] = (title, host, deadline, kind)
        except Exception as e:
            fails += 1
            print("list fail", u, e, file=sys.stderr)
        time.sleep(0.5)
    if fails > len(urls) / 2:  # 네트워크 끊김·차단: 빈 결과로 기존 데이터를 덮어쓰지 않도록 이 소스는 실패 처리
        raise RuntimeError(f"목록 {fails}/{len(urls)}건 실패")
    out = []
    for ix, (title, host, deadline, kind) in cand.items():
        url = f"https://www.wevity.com/?c=find&s=1&gub=1&cidx=20&gbn=view&ix={ix}"
        extra = {}
        try:
            extra = wevity_detail(get(url), today, title, host)
            time.sleep(0.5)
        except Exception as e:
            print("detail fail", url, e, file=sys.stderr)
        kind = final_kind(kind, extra)
        if not kind:
            continue
        out.append({**extra, "id": f"wevity-{ix}", "source": "위비티", "kind": kind, "title": title,
                    "host": host, "deadline": deadline, "url": url})
    return out


def linkareer_state(url):
    html = get(url)
    data = json.loads(re.search(r"__NEXT_DATA__[^>]*>(.*?)</script>", html, re.S).group(1))
    return data["props"]["pageProps"]["__APOLLO_STATE__"]


def linkareer(today):
    base = "https://linkareer.com/list/contest?filterType=CATEGORY&orderBy_direction=DESC&orderBy_field=CREATED_AT"
    urls = [(f"{base}&filterBy_q={urllib.parse.quote(t)}&page={p}", t in BODY_TERMS)
            for t in SEARCH_TERMS for p in range(1, SEARCH_PAGES + 1)] + [
        (f"{base}&filterBy_categoryIDs=35&page={p}", False) for p in range(1, CATEGORY_PAGES + 1)]
    cand, fails = {}, 0
    for u, body_ok in urls:
        try:
            for k, v in linkareer_state(u).items():
                if not k.startswith("Activity:"):
                    continue
                kind = kind_of(v.get("title", ""))
                if (kind or body_ok) and not (v["id"] in cand and cand[v["id"]][1] and not kind):
                    cand[v["id"]] = (v, kind)
        except Exception as e:
            fails += 1
            print("list fail", u, e, file=sys.stderr)
        time.sleep(0.5)
    if fails > len(urls) / 2:
        raise RuntimeError(f"목록 {fails}/{len(urls)}건 실패")
    out = []
    for aid, (v, kind) in cand.items():
        close = v.get("recruitCloseAt")
        if close and datetime.fromtimestamp(close / 1000, KST).date() < today:
            continue
        extra = {}
        try:
            dstate = linkareer_state(f"https://linkareer.com/activity/{aid}")
            act = dstate.get(f"Activity:{aid}", v)
            if act.get("status") not in (None, "OPEN"):  # 사이트 쪽에서 이미 접수 종료
                continue
            extra = linkareer_detail(act, dstate, today)
            time.sleep(0.5)
        except Exception as e:
            print("detail fail", aid, e, file=sys.stderr)
        kind = final_kind(kind, extra)
        if not kind:
            continue
        out.append({
            **extra, "id": f"linkareer-{aid}", "source": "링커리어", "kind": kind, "title": v["title"],
            "host": v.get("organizationName") or "",
            "deadline": datetime.fromtimestamp(close / 1000, KST).date().isoformat() if close else None,
            "url": f"https://linkareer.com/activity/{aid}",
        })
    return out


def norm_title(t):
    t = re.sub(r"20\d\d년?|제?\s?\d+\s?회|참(?:가|여)자\s?모집|모집|공모전|대회|프로젝트", "", t.lower())
    return re.sub(r"[^0-9a-z가-힣]", "", t)


def merge_duplicates(items):
    """사이트가 달라도 같은 대회면 한 건으로 합친다 (정보가 더 많은 쪽 + 빈 칸 보충)."""
    info = lambda it: sum(v not in (None, "", [], False) for v in it.values())
    groups = []
    for it in sorted(items, key=info, reverse=True):
        k = norm_title(it["title"])
        for g in groups:
            gk = g["key"]
            if k == gk or (min(len(k), len(gk)) >= 8 and (k in gk or gk in k)):
                g["members"].append(it)
                break
        else:
            groups.append({"key": k, "members": [it]})
    out = []
    for g in groups:
        best = dict(g["members"][0])
        for other in g["members"][1:]:
            for f, v in other.items():
                if best.get(f) in (None, "", []) and v not in (None, "", []):
                    best[f] = v
        best["source"] = " · ".join(dict.fromkeys(m["source"] for m in g["members"]))
        best["merged_ids"] = [m["id"] for m in g["members"]]
        out.append(best)
    return out


def main():
    now = datetime.now(KST)
    today = now.date()
    old = {}
    if DATA.exists():
        old = {i["id"]: i for i in json.loads(DATA.read_text(encoding="utf-8"))["items"]}
    found, errors = {}, []
    for name, fn in (("wevity", wevity), ("linkareer", linkareer)):
        try:
            for it in fn(today):
                found[it["id"]] = it
        except Exception as e:  # 한 곳이 깨져도 나머지는 계속
            errors.append(f"{name}: {e}")
            print("ERROR", name, e, file=sys.stderr)
    first_run = not old
    # 합쳐진 항목의 대표가 바뀌어도 처음 본 시각을 잃지 않도록 모든 id 기준으로 기억
    old_seen = {m: o["first_seen"] for o in old.values() for m in o.get("merged_ids", [o["id"]])}
    merged = merge_duplicates(list(found.values()))
    for it in merged:
        seen = [old_seen[i] for i in it["merged_ids"] if i in old_seen]
        it["first_seen"] = min(seen) if seen else now.isoformat(timespec="seconds")
    # 이번에 안 잡힌 기존 항목은 마감 안 지났으면 유지 (수집 실패 대비)
    covered = {i for it in merged for i in it["merged_ids"]}
    for i, it in old.items():
        if i not in covered and (not it.get("deadline") or it["deadline"] >= today.isoformat()):
            merged.append(it)
    items = sorted(merged, key=lambda x: x["first_seen"], reverse=True)
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(
        json.dumps({"updated": now.isoformat(timespec="seconds"), "errors": errors, "items": items},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    new = [i for i in items if not any(m in old_seen for m in i.get("merged_ids", [i["id"]]))]
    core = sum(1 for i in items if i.get("kind") == "core")
    print(f"총 {len(items)}건 (해커톤류 {core}, 개발 경진대회 {len(items) - core}), 신규 {0 if first_run else len(new)}건")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

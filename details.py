"""상세 페이지에서 상금·대상·주제·행사 일정을 뽑는 파서"""
import re
from datetime import date, datetime, timedelta, timezone
from html import unescape

KST = timezone(timedelta(hours=9))
EVENT_KW = re.compile(r"본선|해커톤|행사|개최|진행|오프라인|킥오프|발대식|대회|캠프|일시|심사|발표|시상|PT|데모")
EXCL_KW = re.compile(r"접수|모집|신청|지원|제출|서류|결과|공고|설명회|문의|마감|사전|등록|선정|진출팀|참가팀|안내")
DATE = re.compile(r"(?:(20\d{2})\s*[.\-/년]\s*)?(\d{1,2})\s*[.\-/월]\s*(\d{1,2})(?![\d:])\s*일?")
RANGE_TAIL = re.compile(
    r"\.?\s*(?:\([^)]*\))?\s*(?:\d{1,2}:\d{2})?\s*[~∼–—\-]\s*(?:(?:20\d{2}\s*[.\-/년]\s*)?(\d{1,2})\s*[.\-/월]\s*)?(\d{1,2})(?![\d:])"
)
TOPIC_RE = re.compile(r"(?:주제|테마|과제)\s*[:：]\s*([^\n]{3,80})")
TAGS = {
    "AI": r"\bAI\b|인공지능|생성형|LLM|머신러닝|딥러닝",
    "데이터": r"데이터|빅데이터",
    "공공": r"공공|지자체|행정|지역문제|나라장터|시민",
    "환경": r"환경|기후|탄소|ESG|에너지",
    "금융": r"금융|핀테크|결제|보험",
    "헬스케어": r"헬스|의료|건강|바이오",
    "모빌리티": r"모빌리티|자동차|차량|자율주행",
    "교육": r"교육|에듀|학습",
    "게임": r"게임",
    "보안": r"보안|해킹|CTF",
    "창업": r"창업|스타트업|IR",
}


SEOUL = re.compile(r"(?i)seoul|서울|강남|역삼|성수|종로|마포|서초|송파|영등포|여의도|구로|용산|광진|성북|동대문|홍대|신촌|충정로|을지로|중림로|삼성동")
REGIONS = [  # (표시명, 정규식) — 서울 외 지역
    ("경기", r"경기|판교|수원|성남|용인|고양|안양|화성|평택|부천|안산|파주"),
    ("인천", r"인천|송도"),
    ("부산", r"부산"), ("대구", r"대구"), ("대전", r"대전|KAIST|카이스트"), ("광주", r"광주"), ("울산", r"울산"),
    ("세종", r"세종"),
    ("강원", r"강원|동해|춘천|원주|강릉|속초"),
    ("충북", r"충북|청주|충주"), ("충남", r"충남|천안|아산|공주"),
    ("전북", r"전북|전주|익산"), ("전남", r"전남|여수|순천|목포"),
    ("경북", r"경북|포항|경주|구미|안동"), ("경남", r"경남|경상국립|진주|창원|김해"),
    ("제주", r"제주"),
]
TRAVEL = re.compile(r"교통비(?!\s*(?:미|불))|교통\s*지원|여비")
LOC_LINE = re.compile(r"(?:본선\s*|오프라인\s*|행사\s*)?(?:장소|개최\s*지|개최\s*장소)\s*[:：]\s*([^\n]{2,70})")


# 현장에 가야 하는 행사인지 보는 단서 (발표·심사·본선·캠프·장소 표기 등)
IN_PERSON = re.compile(
    r"오프라인|대면|현장\s*(?:발표|심사|참석|참여|평가|접수|방문|시상)|본선\s*(?:대회|발표|심사|장소|진출)"
    r"|최종\s*(?:PT|발표|심사)\s*\(?(?:오프라인|현장)|\d\s*박\s*\d\s*일|숙박\s*(?:제공|지원)|캠프|대회장|집결|발대식|참석\s*필수"
)
ONLINE_ONLY = re.compile(
    r"(?:전\s*과정|100\s*%|모든\s*과정|전면)\s*(?:온라인|비대면)|비대면\s*(?:으로)?\s*(?:진행|개최|심사|평가)|온라인\s*(?:으로\s*)?(?:진행|개최)"
    r"|(?:온라인|이메일|웹|홈페이지|구글\s?폼)\s*(?:으로\s*)?(?:작품\s*)?제출"
)


def locate(body, title, host, event_text):
    """장소·지역·현장 참석 필요 여부·교통비 지원 여부.

    서울 기준 필터용이라 '어디서 열리나'보다 '현장에 가야 하나'가 먼저다.
    inperson=False면 온라인 제출형(현장 참석 없음)이라 지역은 의미가 없다.
    """
    m = LOC_LINE.search(body)
    place = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
    in_lines = [l for l in body.split("\n") if IN_PERSON.search(l)]
    strong = bool(place) or bool(in_lines)
    if strong and not place and ONLINE_ONLY.search(body) and not re.search(r"오프라인|대면|\d\s*박\s*\d\s*일|숙박", body):
        strong = False  # 온라인 제출/진행만 언급
    # 이벤트 줄이 온라인이면 현장 장소가 따로 적혀 있지 않은 한 온라인 개최
    online = bool(event_text and re.search(r"온라인", event_text)) and not place
    inperson = strong and not online
    region = None
    if inperson:
        for src in (place, " ".join(in_lines), event_text, title + " " + host):
            if not src:
                continue
            if SEOUL.search(src):
                region = "서울"
                break
            hit = next((n for n, rx in REGIONS if re.search(rx, src)), None)
            if hit:
                region = hit
                break
    return {"place": place, "region": region, "online": online, "inperson": inperson,
            "travel": bool(TRAVEL.search(body))}


SOLO_NO = re.compile(r"개인\s*(?:참가|참여|신청|지원)?\s*(?:은\s*)?불가|팀\s*(?:단위\s*(?:로만\s*)?|으로만\s*|만\s*)(?:참가|참여|신청|접수)|팀\s*참가만")
SOLO_YES = re.compile(
    r"개인\s*(?:또는|혹은|및|/|,|·|전)\s*팀|팀\s*(?:또는|혹은|및|/|,|·)\s*개인|개인\s*(?:참가|참여|신청|지원|가능)"
    r"|1\s*인\s*(?:참가|참여|신청|팀)|개인\s*자격|혼자\s*(?:참가|참여)"
)
TEAM_SIZE = re.compile(r"(\d)\s*[~∼\-–]\s*(\d)\s*(?:인|명)|(?:팀당|팀\s*당|팀\s*구성)[^\n\d]{0,8}(\d)\s*(?:인|명)")


FEE_RE = re.compile(r"(?:참가|참여|신청|등록)\s*(?:비용|비|료)\s*[:：]?\s*(?:\n\s*)?([^\n]{0,40})")


def fee_info(body):
    """참가비: 금액이 적혀 있으면 paid=True, 무료/없음이면 False, 언급이 없으면 None"""
    verdict, text = None, None
    for m in FEE_RE.finditer(body):
        s = m.group(1).strip()
        if re.search(r"[1-9][\d,]*\s*(?:만\s*)?원|유료", s):  # 금액이 있으면 무료 문구보다 우선
            return {"paid": True, "fee": s[:30]}
        if re.search(r"무료|없음|없습니다|(?<![\d,])0\s?원|무상|free", s, re.I):
            verdict, text = False, s[:20] or "무료"
        elif re.search(r"\d[\d,]*\s*(?:만\s*)?원|유료", s):
            return {"paid": True, "fee": s[:30]}
    return {"paid": verdict, "fee": text}


def participation(body):
    """개인 참가 가능 여부(True/False/None)와 팀 인원 문구"""
    solo = False if SOLO_NO.search(body) else (True if SOLO_YES.search(body) else None)
    m = TEAM_SIZE.search(body)
    size = None
    if m:
        size = f"{m.group(1)}~{m.group(2)}인" if m.group(1) else f"최대 {m.group(3)}인"
    return solo, size


def plain(html):
    html = re.sub(r"<(script|style).*?</\1>", "", html, flags=re.S)
    html = re.sub(r"<br\s*/?>|</p>|</li>|</tr>|</div>|</h\d>", "\n", html, flags=re.I)
    t = unescape(re.sub(r"<[^>]+>", " ", html)).replace("\xa0", " ")
    return "\n".join(l.strip() for l in re.sub(r"[ \t]+", " ", t).split("\n") if l.strip())


def to_won(s):
    """'5,100만원' '1천만원' '1억 원' -> 원 단위 정수, 못 읽으면 None"""
    s = s.replace(",", "").replace(" ", "")
    m = re.search(r"(\d+(?:\.\d+)?)(억|천만|백만|만)?", s)
    if not m:
        return None
    unit = {"억": 10**8, "천만": 10**7, "백만": 10**6, "만": 10**4, None: 1}[m.group(2)]
    return int(float(m.group(1)) * unit)


def fmt_won(w):
    if not w:
        return None
    if w >= 10**8 and w % 10**7 == 0:
        return f"{w / 10**8:g}억원"
    if w >= 10**4:
        return f"{w // 10**4:,}만원"
    return f"{w:,}원"


def parse_event(text, today):
    best = None
    for line in text.split("\n"):
        if not EVENT_KW.search(line) or EXCL_KW.search(line):
            continue
        m = DATE.search(line)
        if not m:
            continue
        y = int(m.group(1)) if m.group(1) else today.year
        try:
            start = date(y, int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if not m.group(1) and start < today - timedelta(days=60):
            start = date(y + 1, start.month, start.day)
        end = start
        t = RANGE_TAIL.match(line, m.end())
        if t:
            try:
                e = date(start.year, int(t.group(1)) if t.group(1) else start.month, int(t.group(2)))
                if 0 <= (e - start).days <= 14:
                    end = e
            except ValueError:
                pass
        if end < today:
            continue
        if best is None or start < best[0]:
            best = (start, end, re.sub(r"^[\-•·○■▶\s]+", "", line)[:90])
    return best


def weekend_in(start, end):
    d = start
    while d <= end:
        if d.weekday() >= 5:
            return True
        d += timedelta(days=1)
    return False


def analyze(body, target_hint, prize_total, prize_first, today, title="", host=""):
    out = {}
    pt = prize_total
    if not pt:
        m = re.search(r"총\s*(?:상금|시상금|규모)[^\d\n]{0,10}([\d,\.]+\s*(?:억|천만|백만|만)?\s*원)", body)
        pt = m.group(1) if m else None
    if not pt:
        m = re.search(r"(?:상금|시상금)[^\d\n]{0,12}([\d,\.]+\s*(?:억|천만|백만|만)\s*원)", body)
        pt = m.group(1) if m else None
    out["prize"] = pt
    out["prize_won"] = to_won(pt) if pt and re.search(r"\d", pt) else None
    if not out["prize_won"]:  # 총상금 표기가 없으면 '대상 200만원' 같은 시상 줄에서 가장 큰 금액을 사용
        amounts = []
        for line in body.split("\n"):
            if re.search(r"대상|1등|1위|최우수|우승|상금|시상", line):
                for a in re.findall(r"\d[\d,\.]*\s*(?:억|천만|백만|만)\s*원|\d{1,3}(?:,\d{3})+\s*원", line):
                    w = to_won(a)
                    if w and w >= 10**5:
                        amounts.append((w, a))
        if amounts:
            w, a = max(amounts)
            out["prize"], out["prize_won"] = re.sub(r"\s+", "", a), w
    out["prize_first"] = prize_first or None
    tgt = (target_hint or "").strip()
    out["target"] = tgt or None
    out["univ"] = bool(re.search(r"대학|재학생|휴학", tgt)) or bool(
        re.search(r"(?:참가|참여|응모|지원)\s*(?:대상|자격)[^\n]{0,80}(?:대학|재학)|대학생|대학원생", body)
    )
    m = TOPIC_RE.search(body)
    out["topic"] = m.group(1).strip(" -·") if m else None
    out["tags"] = [k for k, rx in TAGS.items() if re.search(rx, body[:2500], re.I)][:4]
    ev = parse_event(body, today)
    if ev:
        out["event_start"], out["event_end"], out["event_text"] = ev[0].isoformat(), ev[1].isoformat(), ev[2]
        out["weekend"] = weekend_in(ev[0], ev[1])
    else:
        out["event_start"] = out["event_end"] = out["event_text"] = out["weekend"] = None
    out.update(locate(body, title, host, out["event_text"]))
    out["solo"], out["team_size"] = participation(body)
    if len(body.strip()) < 150:  # 본문을 못 읽었으면 현장 참석 여부는 모름
        out["inperson"] = None
    # 제목엔 없어도 본문이 해커톤·바이브코딩·잼 성격이면 해커톤류로 올리기 위한 신호
    out["hack_mentions"] = len(re.findall(
        r"바이브\s?코딩|vibe\s?coding|해커\s?톤|hackathon|게임\s?잼|game\s?jam|\bjam\b"
        r"|생성형\s?AI\s?툴|AI\s?(?:를|로)\s?활용(?:하여|해)\s?(?:제작|개발)|AI\s?활용\s?(?:게임|앱|서비스)", body, re.I))
    out.update(fee_info(body))
    # 현금 상금이 아닌 경우(구독권·이용권·크레딧 등)를 구분: 숫자 상금이 없고 이런 보상만 적혀 있으면 상금 없음으로 본다
    out["noncash"] = bool(
        not out["prize_won"]
        and re.search(r"(?:1\s?위|1등|종합|대상|우승|최우수|참가자\s?전원|시상|상품|혜택)[^\n]{0,60}(?:구독|\d\s?개월|이용권|크레딧|쿠폰|Pro\b|Plus\b|라이선스)", body)
    )
    return out


def wevity_detail(html, today, title="", host=""):
    t = plain(html)
    flat = re.sub(r"\s+", " ", t)
    flat = flat[flat.find("조회수") :] if "조회수" in flat else flat  # 상단 메뉴 글자 제외

    def g(rx):
        m = re.search(rx, flat)
        return m.group(1).strip() if m else None

    i = t.find("상세내용")
    body = (t[i:] if i >= 0 else t).split("본 정보의 사실 여부")[0]
    pt = g(r"총 상금 (.*?) 1등 상금")
    # '1천만원이하' 같은 범위 표기는 부정확하니 본문 수치를 우선
    r = analyze(body, g(r"응모대상 (.*?) 주최/주관"), None if (pt and re.search(r"이하|이상", pt)) else pt,
                g(r"1등 상금 (.*?) (?:홈페이지|첨부)"), today, title, host)
    if not r["prize"]:
        r["prize"] = pt
    a = re.search(r"접수기간 (\d{4}-\d\d-\d\d) ~", flat)
    if a:
        r["apply_start"] = a.group(1)
    return r


def linkareer_detail(act, state, today):
    text = ""
    ref = (act.get("detailText") or {}).get("__ref")
    if ref and ref in state:
        text = plain(state[ref].get("text", ""))
    names = [state.get(t["__ref"], {}).get("name", "") for t in act.get("targets") or []]
    unit = act.get("tenThousandUnitOfReward")
    r = analyze(text, ", ".join(n for n in names if n), fmt_won(unit * 10**4) if unit else None, None, today,
                act.get("title", ""), act.get("organizationName") or "")
    if act.get("recruitStartAt"):
        r["apply_start"] = datetime.fromtimestamp(act["recruitStartAt"] / 1000, KST).date().isoformat()
    return r

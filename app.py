import streamlit as st
import pandas as pd
import io
import os
import time
import random
import base64
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

st.set_page_config(
    page_title="구매대행 소싱 대시보드",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    div[data-testid="metric-container"] {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 12px 16px;
    }
    /* 테이블 헤더 강조 */
    .tbl-header {
        font-size: 0.78rem;
        font-weight: 700;
        color: #495057;
        padding-bottom: 4px;
    }
    /* 테이블 행 구분선 */
    .tbl-divider {
        border: none;
        border-top: 1px solid #e9ecef;
        margin: 2px 0;
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# 세션 상태 초기화
# ══════════════════════════════════════════════════════════════════
if "ai_results" not in st.session_state:
    st.session_state.ai_results: dict = {}
if "pending_analysis" not in st.session_state:
    st.session_state.pending_analysis: str | None = None


# ══════════════════════════════════════════════════════════════════
# Playwright + Claude API 분석 함수
# ══════════════════════════════════════════════════════════════════
def run_playwright_claude_analysis(keyword: str, api_key: str) -> dict:
    """
    1. Playwright로 쿠팡 검색 → 스크롤 → 스크린샷
    2. Claude API(멀티모달)로 구매대행 상품 수 분석
    반환: {"overseas": int, "total": int, "screenshot_path": str}
    """
    from playwright.sync_api import sync_playwright
    import anthropic
    from PIL import Image
    import io as _io

    # ── Playwright ────────────────────────────────────────────────
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--start-maximized",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        # webdriver 흔적 숨김
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()

        url = (
            "https://www.coupang.com/np/search?"
            f"q={urllib.parse.quote(keyword)}&channel=user"
        )
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(random.uniform(2.5, 4.0))  # 사람처럼 대기

        # 천천히 스크롤 (사람처럼)
        page.evaluate("""
            new Promise(resolve => {
                let total = 0;
                const dist = 250;
                const timer = setInterval(() => {
                    window.scrollBy(0, dist);
                    total += dist;
                    if (total >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 90);
            })
        """)
        time.sleep(random.uniform(1.5, 2.5))

        raw_bytes = page.screenshot(full_page=True)
        browser.close()

    # ── 스크린샷 저장 ─────────────────────────────────────────────
    tmp_dir = Path(os.getenv("TEMP", "/tmp")) / "sourcing_screenshots"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = tmp_dir / f"{keyword}_{ts}.png"
    screenshot_path.write_bytes(raw_bytes)

    # ── 이미지 리사이즈 (Claude API 용량 제한 대응) ───────────────
    img = Image.open(_io.BytesIO(raw_bytes))
    MAX_H = 5_000
    if img.height > MAX_H:
        ratio = MAX_H / img.height
        img = img.resize((int(img.width * ratio), MAX_H), Image.LANCZOS)
    buf = _io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    resized_bytes = buf.getvalue()

    # ── Claude API ────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    img_b64 = base64.standard_b64encode(resized_bytes).decode()
    today = datetime.now().strftime("%Y년 %m월 %d일")

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        f"오늘은 {today}입니다.\n"
                        "이 쿠팡 검색 결과 이미지를 분석해주세요.\n\n"
                        "1. 첫 페이지에 보이는 전체 상품 수를 세어주세요.\n"
                        f"2. 각 상품의 배송 예정일을 확인하여, {today} 기준으로 "
                        "배송 완료까지 8일 이상 걸리는 구매대행/해외배송 상품 수를 세어주세요.\n\n"
                        "아래 JSON 형식으로만 답변하세요. 다른 텍스트 없이 JSON만 출력하세요:\n"
                        '{"total": 전체상품수, "overseas": 8일이상_구매대행수}'
                    ),
                },
            ],
        }],
    )

    text = resp.content[0].text.strip()
    m = re.search(r'\{[^}]+\}', text)
    if m:
        data = json.loads(m.group())
        return {
            "overseas": int(data.get("overseas", 0)),
            "total": int(data.get("total", 0)),
            "screenshot_path": str(screenshot_path),
            "analyzed_at": datetime.now().strftime("%H:%M"),
        }
    raise ValueError(f"Claude 응답 파싱 실패: {text}")


def _overseas_label(overseas: int, total: int) -> tuple[str, str]:
    """구매대행 수 → (상태 레이블, 색상)"""
    if total == 0:
        return "❓ 분석불가", "⬜"
    if overseas == 0:
        return "❌ 구대 없음", "red"
    if overseas < 5:
        return "⚠️ 너무 적음", "orange"
    if overseas <= 10:
        return "✅ 황금구간", "green"
    return "🟡 경쟁 많음", "blue"


# ══════════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ 필터 설정")
    st.divider()

    st.subheader("쿠팡 배송")
    rocket_max = st.slider("로켓배송비율 상한 (%)", 0, 100, 40, 5,
                           help="이 값 미만인 키워드만 통과")
    overseas_ratio_min = st.slider("해외배송비율 하한 (%)", 0, 50, 10, 5,
                                   help="이 값 이상인 키워드만 통과")

    st.subheader("리뷰")
    overseas_total_min = st.number_input("해외배송 총리뷰 최소", min_value=0, value=1, step=1,
                                         help="0이면 실제 판매 없음 → 제외")
    overseas_avg_min = st.number_input("해외배송 평균리뷰 최소", min_value=0, value=5, step=1,
                                       help="실거래 증거 기준")

    st.subheader("검색량")
    search_min = st.number_input("최근 1개월 검색량 최소", min_value=0, value=5000, step=500)

    st.subheader("키워드 타입")
    exclude_brand   = st.checkbox("브랜드 키워드 제외",       value=True)
    require_shopping = st.checkbox("쇼핑성 키워드만 포함",    value=True)
    include_seasonal = st.checkbox("계절성 키워드 포함 (⚠️ 태그)", value=True,
                                   help="체크 해제 시 계절성 키워드 탈락")

    st.divider()
    st.subheader("📊 판매자 검증 기준")
    st.caption("판매자 분석 가이드 탭에서 사용됩니다")
    chk_sales_qty   = st.number_input("① 월 판매량 기준 (개 이상)",   min_value=0, value=50,  step=10)
    chk_revenue     = st.number_input("② 월 매출액 기준 (만원 이상)", min_value=0, value=300, step=50)
    chk_competitors = st.number_input("③ 경쟁 셀러 기준 (명 이하)",   min_value=0, value=10,  step=1)

    st.divider()
    st.subheader("🤖 AI 분석 설정")
    st.caption("쿠팡 AI 자동 분석 기능에 필요합니다.\n로컬 실행 전용 기능입니다.")
    api_key_input = st.text_input(
        "Anthropic API Key",
        type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        placeholder="sk-ant-...",
    )


# ══════════════════════════════════════════════════════════════════
# 메인 헤더 + 파일 업로드
# ══════════════════════════════════════════════════════════════════
st.title("🔍 구매대행 소싱 대시보드")
st.caption("셀러라이프 키워드 데이터 업로드 → 황금 키워드 필터링 → 쿠팡 AI 자동 분석 → 판매자 교차 검증")

uploaded_file = st.file_uploader(
    "📂 엑셀 파일 업로드 (.xlsx / .xls / .csv)",
    type=["xlsx", "xls", "csv"],
    help="셀러라이프에서 다운로드한 키워드 분석 파일을 올려주세요.",
)

if uploaded_file is None:
    st.info("👆 파일을 업로드하면 자동으로 필터링이 시작됩니다.")
    with st.expander("📋 현재 설정된 필터 기준 보기"):
        st.markdown(f"""
| # | 조건 | 기준값 |
|---|------|--------|
| ① | 쿠팡 로켓배송비율 | **{rocket_max}% 미만** |
| ② | 쿠팡 해외배송 총리뷰수 | **{overseas_total_min}개 이상** |
| ③ | 쿠팡 해외배송비율 | **{overseas_ratio_min}% 이상** |
| ④ | 브랜드 키워드 | **X (비브랜드)만 통과** |
| ⑤ | 쇼핑성 키워드 | **O (구매의도)만 통과** |
| ⑥ | 쿠팡 해외배송 평균리뷰 | **{overseas_avg_min}개 이상** |
| ⑦ | 최근 1개월 검색량 | **{search_min:,} 이상** |
""")
    st.stop()


# ══════════════════════════════════════════════════════════════════
# 데이터 로딩
# ══════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def load_data(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    if file_name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(file_bytes))
    return pd.read_excel(io.BytesIO(file_bytes))


with st.spinner("파일 불러오는 중..."):
    try:
        raw_bytes = uploaded_file.read()
        df_raw = load_data(raw_bytes, uploaded_file.name)
    except Exception as e:
        st.error(f"파일 읽기 실패: {e}")
        st.stop()

df = df_raw.copy()
df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]

# 중복 제거 (검색량 높은 행 우선)
_before_dedup = len(df)
if "키워드" in df.columns and "최근 1개월 검색량" in df.columns:
    df = (
        df.sort_values("최근 1개월 검색량", ascending=False)
          .drop_duplicates(subset="키워드", keep="first")
          .reset_index(drop=True)
    )
_dedup_removed = _before_dedup - len(df)

REQUIRED = [
    "키워드", "카테고리", "브랜드 키워드", "쇼핑성 키워드", "계절성",
    "최근 1개월 검색량",
    "쿠팡 로켓배송비율", "쿠팡 해외배송비율",
    "쿠팡 해외배송 총리뷰수", "쿠팡 해외배송 평균리뷰수",
]
missing = [c for c in REQUIRED if c not in df.columns]
if missing:
    st.error("필수 컬럼을 찾을 수 없습니다.")
    st.write("**없는 컬럼:**", missing)
    st.write("**현재 파일 컬럼:**", list(df.columns))
    st.stop()


# ══════════════════════════════════════════════════════════════════
# 필터 적용
# ══════════════════════════════════════════════════════════════════
total = len(df)

filters: dict[str, pd.Series] = {
    f"① 로켓배송비율 < {rocket_max}%":
        df["쿠팡 로켓배송비율"] < (rocket_max / 100),
    f"② 해외배송 총리뷰 ≥ {overseas_total_min}":
        df["쿠팡 해외배송 총리뷰수"] >= overseas_total_min,
    f"③ 해외배송비율 ≥ {overseas_ratio_min}%":
        df["쿠팡 해외배송비율"] >= (overseas_ratio_min / 100),
    "④ 브랜드 키워드 X":
        df["브랜드 키워드"] == "X" if exclude_brand else pd.Series(True, index=df.index),
    "⑤ 쇼핑성 키워드 O":
        df["쇼핑성 키워드"] == "O" if require_shopping else pd.Series(True, index=df.index),
    f"⑥ 해외배송 평균리뷰 ≥ {overseas_avg_min}":
        df["쿠팡 해외배송 평균리뷰수"] >= overseas_avg_min,
    f"⑦ 1개월 검색량 ≥ {search_min:,}":
        df["최근 1개월 검색량"] >= search_min,
}
if not include_seasonal:
    filters["⑧ 계절성 없음"] = df["계절성"] == "없음"

pass_mask  = pd.Series(True, index=df.index)
first_fail = pd.Series("✅ 통과", index=df.index)
for fname, fmask in filters.items():
    newly_failed = pass_mask & ~fmask
    first_fail[newly_failed] = fname
    pass_mask &= fmask

df["_필터결과"] = first_fail
df_pass = df[pass_mask].copy()
df_pass["계절태그"] = df_pass["계절성"].apply(lambda x: "⚠️" if x == "있음" else "-")

n_pass   = len(df_pass)
n_fail   = total - n_pass
pass_rate = n_pass / total * 100 if total > 0 else 0


# ══════════════════════════════════════════════════════════════════
# AI 분석 실행 (버튼 클릭 후 다음 렌더에서 처리)
# ══════════════════════════════════════════════════════════════════
if st.session_state.pending_analysis:
    kw = st.session_state.pending_analysis
    if not api_key_input:
        st.error("사이드바 하단 'Anthropic API Key'를 먼저 입력해주세요.")
        st.session_state.pending_analysis = None
    else:
        with st.spinner(
            f"**'{kw}'** 쿠팡 AI 분석 중...  \n"
            "크롬 브라우저가 자동 실행됩니다. 창을 닫지 마세요. (30~60초 소요)"
        ):
            try:
                result = run_playwright_claude_analysis(kw, api_key_input)
                st.session_state.ai_results[kw] = result
                o, t = result["overseas"], result["total"]
                st.toast(f"'{kw}' 분석 완료 — 구대 {o}개 / 전체 {t}개", icon="✅")
            except Exception as e:
                st.session_state.ai_results[kw] = {"error": str(e)}
                st.error(f"분석 실패: {e}")
            finally:
                st.session_state.pending_analysis = None
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# 요약 지표
# ══════════════════════════════════════════════════════════════════
st.divider()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("원본 행 수",  f"{_before_dedup:,}개")
c2.metric("중복 제거",   f"{_dedup_removed:,}개",
          delta=f"-{_dedup_removed}" if _dedup_removed else None, delta_color="off")
c3.metric("✅ 통과",     f"{n_pass:,}개")
c4.metric("❌ 탈락",     f"{n_fail:,}개")
c5.metric("통과율",      f"{pass_rate:.1f}%")
st.divider()

with st.expander("📊 필터별 탈락 현황"):
    fail_df = (
        df[df["_필터결과"] != "✅ 통과"]["_필터결과"]
        .value_counts().reset_index()
    )
    fail_df.columns = ["탈락 필터", "탈락 수"]
    fail_df["전체 대비 (%)"] = (fail_df["탈락 수"] / total * 100).round(1)
    st.dataframe(fail_df, use_container_width=True, hide_index=True)

if n_pass > 0 and "카테고리" in df_pass.columns:
    with st.expander("📂 카테고리별 통과 키워드 수"):
        cat_df = (
            df_pass.groupby("카테고리")
            .agg(통과수=("키워드", "count"))
            .sort_values("통과수", ascending=False)
            .reset_index()
        )
        st.dataframe(cat_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════
# 탭
# ══════════════════════════════════════════════════════════════════
tab_filter, tab_guide = st.tabs(["🔍 필터 결과", "📋 판매자 분석 가이드"])


# ──────────────────────────────────────────────────────────────────
# TAB 1 : 필터 결과 + AI 분석
# ──────────────────────────────────────────────────────────────────
with tab_filter:
    st.subheader(f"✅ 통과 키워드 — {n_pass:,}개")

    if n_pass == 0:
        st.warning("통과 키워드가 없습니다. 사이드바에서 필터 수치를 완화해보세요.")
    else:
        st.caption(
            "🛒 **쿠팡 열기** → 쿠팡 검색 결과 새 탭  |  "
            "🤖 **AI 분석** → 크롬 자동 실행 후 배송일 기준 구매대행 상품 수 파악  |  "
            "✅황금(5~10개) ⚠️적음(<5) 🟡경쟁많음(>10)"
        )

        # ── 테이블 헤더 ────────────────────────────────────────────
        RATIOS = [2.2, 0.5, 1.2, 0.9, 0.9, 0.7, 1.0, 1.0, 0.8]
        HEADERS = ["키워드", "계절", "검색량", "해외배송%", "해외평균리뷰",
                   "🛒 쿠팡", "🤖 AI분석", "구대/전체", "구대비율"]

        hcols = st.columns(RATIOS)
        for hc, h in zip(hcols, HEADERS):
            hc.markdown(f"<div class='tbl-header'>{h}</div>", unsafe_allow_html=True)
        st.markdown("<hr class='tbl-divider'>", unsafe_allow_html=True)

        # ── 테이블 행 ──────────────────────────────────────────────
        df_sorted = df_pass.sort_values("최근 1개월 검색량", ascending=False)

        for _, row in df_sorted.iterrows():
            kw       = str(row["키워드"])
            ai_res   = st.session_state.ai_results.get(kw)
            cols     = st.columns(RATIOS)

            cols[0].write(f"**{kw}**")
            cols[1].write(row["계절태그"])
            cols[2].write(f"{int(row['최근 1개월 검색량']):,}")
            cols[3].write(f"{row['쿠팡 해외배송비율']*100:.0f}%")
            cols[4].write(f"{row['쿠팡 해외배송 평균리뷰수']:.0f}")

            coupang_url = (
                "https://www.coupang.com/np/search?"
                f"q={urllib.parse.quote(kw)}&channel=user"
            )
            cols[5].link_button("열기", coupang_url, use_container_width=True)

            if ai_res is None:
                # 미분석: AI 분석 버튼
                if cols[6].button("🤖 분석", key=f"ai_{kw}", use_container_width=True):
                    st.session_state.pending_analysis = kw
                    st.rerun()
                cols[7].write("-")
                cols[8].write("-")

            elif "error" in ai_res:
                cols[6].error("오류", icon="❌")
                if cols[6].button("재시도", key=f"retry_{kw}", use_container_width=True):
                    del st.session_state.ai_results[kw]
                    st.session_state.pending_analysis = kw
                    st.rerun()
                cols[7].write("-")
                cols[8].write("-")

            else:
                o = ai_res.get("overseas", 0)
                t = ai_res.get("total", 0)
                label, _ = _overseas_label(o, t)
                cols[6].write(label)
                cols[7].write(f"{o} / {t}")
                cols[8].write(f"{o/t*100:.0f}%" if t > 0 else "-")

                # 스크린샷 확인 링크
                sc_path = ai_res.get("screenshot_path", "")
                if sc_path and Path(sc_path).exists():
                    with cols[6]:
                        with st.popover("📷"):
                            st.image(sc_path, caption="분석에 사용된 스크린샷", use_container_width=True)

            st.markdown("<hr class='tbl-divider'>", unsafe_allow_html=True)

        # ── AI 분석 완료된 결과만 따로 표시 ─────────────────────────
        analyzed = {k: v for k, v in st.session_state.ai_results.items()
                    if "error" not in v and k in df_pass["키워드"].values}
        if analyzed:
            st.markdown("---")
            st.markdown("#### 🤖 AI 분석 결과 요약")
            result_rows = []
            for kw, res in analyzed.items():
                o, t = res.get("overseas", 0), res.get("total", 0)
                label, _ = _overseas_label(o, t)
                result_rows.append({
                    "키워드": kw,
                    "구대/전체": f"{o}/{t}",
                    "구대비율": f"{o/t*100:.0f}%" if t > 0 else "-",
                    "판정": label,
                    "분석시각": res.get("analyzed_at", "-"),
                })
            st.dataframe(
                pd.DataFrame(result_rows),
                use_container_width=True,
                hide_index=True,
            )

        # ── 엑셀 다운로드 ─────────────────────────────────────────
        st.markdown("---")
        dl_df = df_pass.drop(columns=["_필터결과", "계절태그"], errors="ignore").copy()
        # AI 분석 결과 컬럼 추가
        dl_df["AI_구대수"]  = dl_df["키워드"].map(
            lambda k: st.session_state.ai_results.get(k, {}).get("overseas", ""))
        dl_df["AI_전체수"]  = dl_df["키워드"].map(
            lambda k: st.session_state.ai_results.get(k, {}).get("total", ""))
        dl_df["AI_구대비율"] = dl_df.apply(
            lambda r: (
                f"{r['AI_구대수']/r['AI_전체수']*100:.0f}%"
                if isinstance(r["AI_구대수"], int) and isinstance(r["AI_전체수"], int) and r["AI_전체수"] > 0
                else ""
            ), axis=1
        )

        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            dl_df.to_excel(writer, index=False, sheet_name="통과키워드")
            df.rename(columns={"_필터결과": "필터결과"}).to_excel(
                writer, index=False, sheet_name="전체_탈락이유포함"
            )
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label="📥 결과 엑셀 다운로드 (AI 분석 결과 포함)",
            data=out.getvalue(),
            file_name=f"소싱필터_{ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )


# ──────────────────────────────────────────────────────────────────
# TAB 2 : 판매자 분석 가이드
# ──────────────────────────────────────────────────────────────────
with tab_guide:
    st.subheader("📋 쿠팡 판매자 교차 검증")
    st.caption(
        "쿠팡 판매자 전용 페이지에서 확인한 실제 수치를 입력하면 소싱 가능 여부를 자동 판정합니다. "
        "기준값은 사이드바 '판매자 검증 기준'에서 변경하세요."
    )

    if n_pass == 0:
        st.info("필터 통과 키워드가 없습니다. 파일을 업로드하고 필터링을 진행하세요.")
        st.stop()

    kw_list    = df_pass.sort_values("최근 1개월 검색량", ascending=False)["키워드"].tolist()
    selected_kw = st.selectbox("분석할 키워드 선택", kw_list, key="guide_kw",
                               help="필터 통과 키워드 (검색량 내림차순)")

    row = df_pass[df_pass["키워드"] == selected_kw].iloc[0]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("검색량(1개월)", f"{int(row['최근 1개월 검색량']):,}")
    m2.metric("로켓배송비율",  f"{row['쿠팡 로켓배송비율']*100:.1f}%")
    m3.metric("해외배송비율",  f"{row['쿠팡 해외배송비율']*100:.1f}%")
    m4.metric("해외 총리뷰",  f"{int(row['쿠팡 해외배송 총리뷰수']):,}")
    m5.metric("해외 평균리뷰", f"{row['쿠팡 해외배송 평균리뷰수']:.0f}")

    # AI 분석 결과 표시 (있을 경우)
    ai_res = st.session_state.ai_results.get(selected_kw)
    if ai_res and "error" not in ai_res:
        o, t = ai_res.get("overseas", 0), ai_res.get("total", 0)
        label, _ = _overseas_label(o, t)
        st.info(f"🤖 AI 분석 결과: 구매대행 **{o}개** / 전체 **{t}개** → {label}")

    coupang_url = (
        "https://www.coupang.com/np/search?"
        f"q={urllib.parse.quote(str(selected_kw))}&channel=user"
    )
    st.link_button(f"🛒 쿠팡에서 '{selected_kw}' 검색하기", coupang_url,
                   help="※ 배송기간 1주 이상인 상품 = 구매대행 상품")

    st.divider()
    st.markdown("#### 실제 데이터 입력 (쿠팡 판매자 전용 페이지 확인 후 기입)")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"**① 월 판매량**  \n기준: `{chk_sales_qty:,}개 이상`")
        actual_qty = st.number_input("실제 월 판매량 (개)", min_value=0, value=0, step=10,
                                     key=f"qty_{selected_kw}")
        if actual_qty > 0:
            (st.success if actual_qty >= chk_sales_qty else st.error)(
                f"{'✅ 충족' if actual_qty >= chk_sales_qty else '❌ 미달'}  ({actual_qty:,}개)"
            )
        else:
            st.caption("미입력")

    with col2:
        st.markdown(f"**② 월 매출액**  \n기준: `{chk_revenue:,}만원 이상`")
        actual_rev = st.number_input("실제 월 매출액 (만원)", min_value=0, value=0, step=10,
                                     key=f"rev_{selected_kw}")
        if actual_rev > 0:
            (st.success if actual_rev >= chk_revenue else st.error)(
                f"{'✅ 충족' if actual_rev >= chk_revenue else '❌ 미달'}  ({actual_rev:,}만원)"
            )
        else:
            st.caption("미입력")

    with col3:
        st.markdown(f"**③ 경쟁 셀러 수**  \n기준: `{chk_competitors}명 이하`")
        actual_comp = st.number_input("실제 경쟁 셀러 수 (명)", min_value=0, value=0, step=1,
                                      key=f"comp_{selected_kw}")
        if actual_comp > 0:
            (st.success if actual_comp <= chk_competitors else st.error)(
                f"{'✅ 충족' if actual_comp <= chk_competitors else '❌ 초과'}  ({actual_comp}명)"
            )
        else:
            st.caption("미입력")

    st.divider()
    st.markdown("**④ 상위 셀러 스토어 방문 & 효자상품 파악**")
    store_visited = st.checkbox("상위 셀러 스토어를 방문하여 효자상품 목록을 확인했다",
                                key=f"store_{selected_kw}")

    st.markdown("**📝 소싱 메모**")
    st.text_area(
        "메모",
        placeholder="예) 중국어명: 儿童双层床  /  단가 약 12만원  /  디자인 차별화 여지 있음",
        key=f"notes_{selected_kw}",
        height=100,
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("#### 종합 판정")

    qty_ok  = (actual_qty  >= chk_sales_qty)   if actual_qty  > 0 else None
    rev_ok  = (actual_rev  >= chk_revenue)      if actual_rev  > 0 else None
    comp_ok = (actual_comp <= chk_competitors)  if actual_comp > 0 else None

    quant_results  = [r for r in [qty_ok, rev_ok, comp_ok] if r is not None]
    entered_count  = len(quant_results) + (1 if store_visited else 0)

    if entered_count == 0:
        st.info("실제 데이터를 입력하면 종합 판정이 표시됩니다.")
    else:
        passed_count   = sum(1 for r in quant_results if r) + (1 if store_visited else 0)
        total_checked  = len(quant_results) + (1 if store_visited else 0)
        all_passed     = all(quant_results) and store_visited if quant_results else store_visited

        if all_passed and total_checked == 4:
            st.success("✅ 소싱 적합 — 4/4 기준 모두 충족")
        elif passed_count >= 3:
            st.warning(f"🟡 검토 필요 — {passed_count}/{total_checked} 기준 충족")
        else:
            st.error(f"❌ 소싱 부적합 — {passed_count}/{total_checked} 기준 충족")

        detail_rows = [
            {"항목": "① 월 판매량",    "결과": "✅" if qty_ok else ("❌" if qty_ok is False else "⬜"),
             "입력값": f"{actual_qty:,}개"   if actual_qty  > 0 else "미입력"},
            {"항목": "② 월 매출액",    "결과": "✅" if rev_ok else ("❌" if rev_ok is False else "⬜"),
             "입력값": f"{actual_rev:,}만원"  if actual_rev  > 0 else "미입력"},
            {"항목": "③ 경쟁 셀러 수", "결과": "✅" if comp_ok else ("❌" if comp_ok is False else "⬜"),
             "입력값": f"{actual_comp}명"     if actual_comp > 0 else "미입력"},
            {"항목": "④ 스토어 방문",  "결과": "✅" if store_visited else "⬜",
             "입력값": "완료" if store_visited else "미완료"},
        ]
        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

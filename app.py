import streamlit as st
import pandas as pd
import io
import urllib.parse
from datetime import datetime

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
    .verdict-box {
        border-radius: 10px;
        padding: 16px 20px;
        font-size: 1.1rem;
        font-weight: 600;
        text-align: center;
        margin-top: 8px;
    }
    .check-card {
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 10px;
        padding: 16px;
    }
</style>
""", unsafe_allow_html=True)


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
    exclude_brand = st.checkbox("브랜드 키워드 제외", value=True)
    require_shopping = st.checkbox("쇼핑성 키워드만 포함", value=True)
    include_seasonal = st.checkbox("계절성 키워드 포함 (⚠️ 태그)", value=True,
                                   help="체크 해제 시 계절성 키워드 탈락")

    st.divider()

    # ── 판매자 검증 기준 ──────────────────────────────────────────
    st.subheader("📊 판매자 검증 기준")
    st.caption("판매자 분석 가이드 탭에서 사용됩니다")
    chk_sales_qty  = st.number_input("① 월 판매량 기준 (개 이상)",   min_value=0, value=50,  step=10)
    chk_revenue    = st.number_input("② 월 매출액 기준 (만원 이상)", min_value=0, value=300, step=50)
    chk_competitors= st.number_input("③ 경쟁 셀러 기준 (명 이하)",   min_value=0, value=10,  step=1)


# ══════════════════════════════════════════════════════════════════
# 메인 헤더 + 파일 업로드
# ══════════════════════════════════════════════════════════════════
st.title("🔍 구매대행 소싱 대시보드")
st.caption("셀러라이프 키워드 데이터를 업로드하면 황금 키워드 필터링 → 판매자 교차 검증까지 한 화면에서 진행합니다.")

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
def load_data(file_bytes, file_name):
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

# ── 중복 키워드 제거 (검색량 높은 행 우선 유지) ───────────────────────────
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
    st.error("필수 컬럼을 찾을 수 없습니다. 컬럼명을 확인해 주세요.")
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
df_pass["계절태그"] = df_pass["계절성"].apply(lambda x: "⚠️ 계절" if x == "있음" else "-")

n_pass   = len(df_pass)
n_fail   = total - n_pass
pass_rate = n_pass / total * 100 if total > 0 else 0


# ══════════════════════════════════════════════════════════════════
# 요약 지표
# ══════════════════════════════════════════════════════════════════
st.divider()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("원본 행 수",    f"{_before_dedup:,}개")
c2.metric("중복 제거",     f"{_dedup_removed:,}개",
          delta=f"-{_dedup_removed}" if _dedup_removed else None,
          delta_color="off")
c3.metric("✅ 통과",       f"{n_pass:,}개")
c4.metric("❌ 탈락",       f"{n_fail:,}개")
c5.metric("통과율",        f"{pass_rate:.1f}%")
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
# TAB 1 : 필터 결과
# ──────────────────────────────────────────────────────────────────
with tab_filter:
    st.subheader(f"✅ 통과 키워드 — {n_pass:,}개")

    if n_pass == 0:
        st.warning("통과 키워드가 없습니다. 왼쪽 사이드바에서 필터 수치를 완화해보세요.")
    else:
        # 분석 상태: 판매자 가이드 탭에서 데이터 입력 여부 반영
        def get_status(kw):
            qty   = st.session_state.get(f"qty_{kw}",   0)
            rev   = st.session_state.get(f"rev_{kw}",   0)
            comp  = st.session_state.get(f"comp_{kw}",  0)
            store = st.session_state.get(f"store_{kw}", False)
            if qty > 0 or rev > 0 or comp > 0 or store:
                return "🔍 분석중"
            return "⬜ 미검토"

        # 쿠팡 검색 URL 생성
        df_pass["쿠팡_URL"] = df_pass["키워드"].apply(
            lambda k: (
                "https://www.coupang.com/np/search?"
                f"q={urllib.parse.quote(str(k))}&channel=user"
            )
        )
        df_pass["셀록홈즈_URL"] = df_pass["키워드"].apply(
            lambda k: (
                "https://sellochomes.co.kr/sellerlife/coupang-analysis-keyword/"
                f"?keyword={urllib.parse.quote(str(k))}&page=1"
            )
        )
        df_pass["분석상태"] = df_pass["키워드"].apply(get_status)

        DISPLAY_MAP = {
            "분석상태":              "상태",
            "키워드":                "키워드",
            "카테고리":              "카테고리",
            "계절태그":              "계절성",
            "최근 1개월 검색량":     "검색량(1개월)",
            "쿠팡 로켓배송비율":     "로켓배송%",
            "쿠팡 해외배송비율":     "해외배송%",
            "쿠팡 해외배송 총리뷰수": "해외총리뷰",
            "쿠팡 해외배송 평균리뷰수":"해외평균리뷰",
            "쿠팡_URL":             "🛒 쿠팡 검색",
            "셀록홈즈_URL":         "📊 셀록홈즈",
        }

        df_display = (
            df_pass[list(DISPLAY_MAP.keys())]
            .rename(columns=DISPLAY_MAP)
            .sort_values("검색량(1개월)", ascending=False)
            .copy()
        )
        df_display["로켓배송%"] = (df_display["로켓배송%"] * 100).round(1)
        df_display["해외배송%"] = (df_display["해외배송%"] * 100).round(1)

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "상태":          st.column_config.TextColumn("상태", width=80),
                "🛒 쿠팡 검색": st.column_config.LinkColumn(
                    "🛒 쿠팡 검색",
                    display_text="열기",
                    help="클릭하면 쿠팡 검색 결과가 새 탭에서 열립니다\n"
                         "※ 배송기간 1주 이상 = 구매대행 상품",
                ),
                "📊 셀록홈즈": st.column_config.LinkColumn(
                    "📊 셀록홈즈",
                    display_text="열기",
                    help="셀록홈즈 쿠팡 시장분석 · 키워드분석 · 1페이지 상품분석",
                ),
                "검색량(1개월)": st.column_config.NumberColumn(format="%d"),
                "로켓배송%":    st.column_config.NumberColumn(format="%.1f%%"),
                "해외배송%":    st.column_config.NumberColumn(format="%.1f%%"),
                "해외총리뷰":   st.column_config.NumberColumn(format="%d"),
                "해외평균리뷰": st.column_config.NumberColumn(format="%.0f"),
            },
        )

        st.caption("💡 '🛒 쿠팡 검색' 클릭 → 배송기간 1주↑ 상품 확인 | '📊 셀록홈즈' 클릭 → 쿠팡 키워드 1페이지 상품 분석")

        # 엑셀 다운로드
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df_pass.drop(columns=["_필터결과", "계절태그", "쿠팡_URL", "셀록홈즈_URL", "분석상태"],
                         errors="ignore").to_excel(
                writer, index=False, sheet_name="통과키워드"
            )
            df.rename(columns={"_필터결과": "필터결과"}).to_excel(
                writer, index=False, sheet_name="전체_탈락이유포함"
            )
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label="📥 결과 엑셀 다운로드",
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
        "쿠팡 판매자 전용 페이지에서 확인한 실제 수치를 입력하면 소싱 가능 여부를 자동으로 판정합니다. "
        "기준값은 왼쪽 사이드바 하단 '판매자 검증 기준'에서 변경할 수 있습니다."
    )

    if n_pass == 0:
        st.info("필터를 통과한 키워드가 없습니다. 먼저 파일을 업로드하고 필터링을 진행하세요.")
        st.stop()

    # 키워드 선택
    kw_list = df_pass.sort_values("최근 1개월 검색량", ascending=False)["키워드"].tolist()
    selected_kw = st.selectbox(
        "분석할 키워드 선택",
        kw_list,
        key="guide_kw",
        help="필터 통과 키워드 목록 (검색량 내림차순)",
    )

    # 선택 키워드의 필터 지표 요약
    row = df_pass[df_pass["키워드"] == selected_kw].iloc[0]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("검색량(1개월)", f"{int(row['최근 1개월 검색량']):,}")
    m2.metric("로켓배송비율",  f"{row['쿠팡 로켓배송비율']*100:.1f}%")
    m3.metric("해외배송비율",  f"{row['쿠팡 해외배송비율']*100:.1f}%")
    m4.metric("해외 총리뷰",  f"{int(row['쿠팡 해외배송 총리뷰수']):,}")
    m5.metric("해외 평균리뷰", f"{row['쿠팡 해외배송 평균리뷰수']:.0f}")

    # 쿠팡 바로가기
    coupang_url = (
        "https://www.coupang.com/np/search?"
        f"q={urllib.parse.quote(str(selected_kw))}&channel=user"
    )
    st.link_button(
        f"🛒 쿠팡에서 '{selected_kw}' 검색하기",
        coupang_url,
        help="※ 검색 결과에서 배송기간 1주 이상인 상품 = 구매대행 상품",
    )

    st.divider()
    st.markdown("#### 실제 데이터 입력 (쿠팡 판매자 전용 페이지 확인 후 기입)")

    # ── 체크리스트 3개 수치 항목 ────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"**① 월 판매량**  \n기준: `{chk_sales_qty:,}개 이상`")
        actual_qty = st.number_input(
            "실제 월 판매량 (개)", min_value=0, value=0, step=10,
            key=f"qty_{selected_kw}",
        )
        if actual_qty > 0:
            if actual_qty >= chk_sales_qty:
                st.success(f"✅ 충족  ({actual_qty:,}개)")
            else:
                st.error(f"❌ 미달  ({actual_qty:,}개)")
        else:
            st.caption("미입력")

    with col2:
        st.markdown(f"**② 월 매출액**  \n기준: `{chk_revenue:,}만원 이상`")
        actual_rev = st.number_input(
            "실제 월 매출액 (만원)", min_value=0, value=0, step=10,
            key=f"rev_{selected_kw}",
        )
        if actual_rev > 0:
            if actual_rev >= chk_revenue:
                st.success(f"✅ 충족  ({actual_rev:,}만원)")
            else:
                st.error(f"❌ 미달  ({actual_rev:,}만원)")
        else:
            st.caption("미입력")

    with col3:
        st.markdown(f"**③ 경쟁 셀러 수**  \n기준: `{chk_competitors}명 이하`")
        actual_comp = st.number_input(
            "실제 경쟁 셀러 수 (명)", min_value=0, value=0, step=1,
            key=f"comp_{selected_kw}",
        )
        if actual_comp > 0:
            if actual_comp <= chk_competitors:
                st.success(f"✅ 충족  ({actual_comp}명)")
            else:
                st.error(f"❌ 초과  ({actual_comp}명)")
        else:
            st.caption("미입력")

    # ── 정성 체크 ────────────────────────────────────────────────────
    st.divider()
    st.markdown("**④ 상위 셀러 스토어 방문 & 효자상품 파악**")
    store_visited = st.checkbox(
        "상위 셀러 스토어를 방문하여 효자상품 목록을 확인했다",
        key=f"store_{selected_kw}",
    )

    # 메모
    st.markdown("**📝 소싱 메모**")
    st.text_area(
        "이 키워드에 대한 메모 (중국어 상품명, 타오바오 링크, 특이사항 등)",
        placeholder="예) 중국어명: 游戏椅  /  단가 약 8만원대  /  디자인 차별화 여지 있음",
        key=f"notes_{selected_kw}",
        height=100,
        label_visibility="collapsed",
    )

    # ── 종합 판정 ────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 종합 판정")

    qty_ok  = (actual_qty  >= chk_sales_qty)   if actual_qty  > 0 else None
    rev_ok  = (actual_rev  >= chk_revenue)      if actual_rev  > 0 else None
    comp_ok = (actual_comp <= chk_competitors)  if actual_comp > 0 else None

    quant_results = [r for r in [qty_ok, rev_ok, comp_ok] if r is not None]
    entered_count = len(quant_results) + (1 if store_visited else 0)

    if entered_count == 0:
        st.info("실제 데이터를 입력하면 종합 판정이 표시됩니다.")
    else:
        passed_count = sum(1 for r in quant_results if r) + (1 if store_visited else 0)
        total_checked = len(quant_results) + (1 if store_visited else 0)

        all_quant_passed = all(quant_results) if quant_results else True
        all_passed = all_quant_passed and store_visited

        if all_passed and total_checked == 4:
            st.success(f"✅ 소싱 적합 — 4/4 기준 모두 충족")
        elif passed_count >= 3:
            st.warning(f"🟡 검토 필요 — {passed_count}/{total_checked} 기준 충족")
        else:
            st.error(f"❌ 소싱 부적합 — {passed_count}/{total_checked} 기준 충족")

        # 판정 상세
        detail_rows = []
        labels = [
            ("① 월 판매량",    qty_ok,   f"{actual_qty:,}개"   if actual_qty  > 0 else "미입력"),
            ("② 월 매출액",    rev_ok,   f"{actual_rev:,}만원" if actual_rev  > 0 else "미입력"),
            ("③ 경쟁 셀러 수", comp_ok,  f"{actual_comp}명"    if actual_comp > 0 else "미입력"),
            ("④ 스토어 방문",  store_visited if store_visited else None, "완료" if store_visited else "미완료"),
        ]
        for label, result, value in labels:
            if result is True:
                icon = "✅"
            elif result is False:
                icon = "❌"
            else:
                icon = "⬜"
            detail_rows.append({"항목": label, "결과": icon, "입력값": value})

        st.dataframe(
            pd.DataFrame(detail_rows),
            use_container_width=True,
            hide_index=True,
        )

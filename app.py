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
    overseas_ratio_min = st.slider("해외배송비율 하한 (%)", 0, 100, 50, 5,
                                   help="이 값 이상인 키워드만 통과")

    st.subheader("리뷰")
    overseas_total_min = st.number_input("해외배송 총리뷰 최소", min_value=0, value=1, step=1,
                                         help="0이면 실제 판매 없음 → 제외")

    st.subheader("검색량")
    search_min = st.number_input("최근 1개월 검색량 최소", min_value=0, value=1000, step=500)


# ══════════════════════════════════════════════════════════════════
# 메인 헤더 + 파일 업로드
# ══════════════════════════════════════════════════════════════════
st.title("🔍 구매대행 소싱 대시보드")
st.caption("셀러라이프 키워드 데이터를 업로드하면 황금 키워드를 자동으로 필터링합니다.")

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
| ⑤ | 경쟁률 | **1.0 초과** |
| ⑥ | 최근 1개월 검색량 | **{search_min:,} 이상** |
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
    "키워드", "카테고리", "브랜드 키워드", "계절성",
    "최근 1개월 검색량",
    "쿠팡 로켓배송비율", "쿠팡 해외배송비율",
    "쿠팡 해외배송 총리뷰수", "경쟁률",
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
        df["브랜드 키워드"] == "X",
    "⑤ 경쟁률 > 1.0":
        df["경쟁률"] > 1.0,
    f"⑥ 1개월 검색량 ≥ {search_min:,}":
        df["최근 1개월 검색량"] >= search_min,
}

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
# 필터 결과 테이블
# ══════════════════════════════════════════════════════════════════
st.subheader(f"✅ 통과 키워드 — {n_pass:,}개")

if n_pass == 0:
    st.warning("통과 키워드가 없습니다. 왼쪽 사이드바에서 필터 수치를 완화해보세요.")
else:
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

    DISPLAY_MAP = {
        "키워드":                "키워드",
        "카테고리":              "카테고리",
        "계절태그":              "계절성",
        "최근 1개월 검색량":     "검색량(1개월)",
        "쿠팡 로켓배송비율":     "로켓배송%",
        "쿠팡 해외배송비율":     "해외배송%",
        "쿠팡 해외배송 총리뷰수": "해외총리뷰",
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

    # 마킹 session_state 초기화 (파일별)
    mark_key = f"marks_{uploaded_file.name}"
    if mark_key not in st.session_state:
        st.session_state[mark_key] = {}

    # 저장된 마킹 복원
    df_display["마킹"] = df_display["키워드"].map(st.session_state[mark_key]).fillna("")

    edited = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "마킹": st.column_config.SelectboxColumn(
                "마킹",
                options=["", "GOOD", "BAD"],
                required=False,
                width=90,
            ),
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
        },
        disabled=[col for col in df_display.columns if col != "마킹"],
    )

    # 변경된 마킹 저장
    for _, row in edited.iterrows():
        st.session_state[mark_key][row["키워드"]] = row["마킹"]

    st.caption("💡 '🛒 쿠팡 검색' 클릭 → 배송기간 1주↑ 상품 확인 | '📊 셀록홈즈' 클릭 → 쿠팡 키워드 1페이지 상품 분석 | 마킹 열에서 GOOD/BAD 선택 가능")

    # 엑셀 다운로드 (화면 표시 데이터 그대로)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        edited.to_excel(writer, index=False, sheet_name="통과키워드")
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    st.download_button(
        label="📥 결과 엑셀 다운로드",
        data=out.getvalue(),
        file_name=f"소싱필터_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

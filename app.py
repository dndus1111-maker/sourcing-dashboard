import streamlit as st

st.set_page_config(
    page_title="구매대행 소싱 도구",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 사이드바 네비게이션 스타일 ────────────────────────────────────
st.markdown("""
<style>
    /* 네비게이션 링크: 폰트 크기 ↑, 굵기 ↑ */
    [data-testid="stSidebarNav"] a span {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
    }
    /* 네비게이션 링크 패딩 */
    [data-testid="stSidebarNav"] a {
        padding: 0.55rem 0.8rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ── 페이지 등록 ──────────────────────────────────────────────────
pg = st.navigation([
    st.Page(
        "pages/sourcing_dashboard.py",
        title="🔍 구매대행 소싱 대시보드",
        default=True,
    ),
    st.Page(
        "pages/image_translate.py",
        title="🌐 중국어 → 한국어 이미지 번역",
    ),
])

pg.run()

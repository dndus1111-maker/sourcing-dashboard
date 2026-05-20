import streamlit as st
import openai
from datetime import datetime
from utils.image_translator import translate_image, resize_to_width, create_zip

DEFAULT_PROMPT = (
    "이미지의 중국어를 한글로 번역해줘\n"
    "번역 폰트는 지마켓산스 사용해주고, "
    "한국쇼핑몰 상세페이지 스타일로 간결하게 부탁할게. "
    "이미지 사이즈는 가로 780px로 생성해줘"
)

COST_PER_IMAGE = 0.08  # gpt-image-2 예상 단가(USD)


# ── 세션 스테이트 초기화 ─────────────────────────────────────────
for key, default in [
    ("translation_results", []),
    ("translation_errors", []),
    ("is_translating", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("🔑 API 설정")
    api_key = st.text_input(
        "OpenAI API Key",
        type="password",
        placeholder="sk-...",
        help="gpt-image-2 사용을 위한 OpenAI API 키를 입력하세요.",
    )

    st.divider()
    st.header("✏️ 번역 프롬프트")
    prompt = st.text_area(
        "프롬프트 (수정 가능)",
        value=DEFAULT_PROMPT,
        height=140,
        label_visibility="collapsed",
    )


# ══════════════════════════════════════════════════════════════════
# 메인 영역
# ══════════════════════════════════════════════════════════════════
st.title("🌐 중국어 → 한국어 이미지 번역")
st.caption(
    "타오바오 상세페이지 이미지를 업로드하면, "
    "OpenAI gpt-image-2가 중국어 텍스트를 한국어로 번역합니다."
)

# ── 이미지 업로드 ────────────────────────────────────────────────
uploaded_files = st.file_uploader(
    "상세페이지 이미지 업로드 (여러 장 선택 가능)",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

# ── 업로드 미리보기 + 비용 안내 ──────────────────────────────────
if uploaded_files:
    st.subheader(f"📎 업로드된 이미지: {len(uploaded_files)}장")

    # 비용 예상
    est_cost = len(uploaded_files) * COST_PER_IMAGE
    with st.sidebar:
        st.divider()
        st.metric("예상 비용", f"~${est_cost:.2f}")
        st.caption(f"{len(uploaded_files)}장 × ~${COST_PER_IMAGE}")

    # 이미지 미리보기 그리드 (4열)
    cols = st.columns(4)
    for i, f in enumerate(uploaded_files):
        with cols[i % 4]:
            st.image(f, caption=f.name, use_container_width=True)

# ── 번역 실행 ────────────────────────────────────────────────────
can_start = bool(api_key) and bool(uploaded_files) and not st.session_state.is_translating

if st.button("🚀 번역 시작", type="primary", disabled=not can_start):
    # 입력 검증
    if not api_key.startswith("sk-"):
        st.error("유효한 OpenAI API 키를 입력해주세요. (sk-로 시작)")
        st.stop()

    # 상태 초기화
    st.session_state.translation_results = []
    st.session_state.translation_errors = []
    st.session_state.is_translating = True

    client = openai.OpenAI(api_key=api_key)

    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(uploaded_files)

    auth_failed = False

    for i, img_file in enumerate(uploaded_files):
        status_text.text(f"번역 중... ({i + 1}/{total}) — {img_file.name}")

        img_bytes = img_file.read()
        result_bytes, error = translate_image(client, img_bytes, img_file.name, prompt)

        if error:
            st.session_state.translation_errors.append((img_file.name, error))
            # API 키 오류면 전체 중단
            if "API 키" in error:
                auth_failed = True
                break
        else:
            resized = resize_to_width(result_bytes, 780)
            st.session_state.translation_results.append((img_file.name, resized))

        progress_bar.progress((i + 1) / total)

    st.session_state.is_translating = False

    if auth_failed:
        status_text.text("")
        st.error("API 키가 유효하지 않습니다. 사이드바에서 키를 확인해주세요.")
    else:
        ok = len(st.session_state.translation_results)
        fail = len(st.session_state.translation_errors)
        status_text.text(f"✅ 완료! 성공: {ok}장 / 실패: {fail}장")

    st.rerun()


# ══════════════════════════════════════════════════════════════════
# 결과 표시
# ══════════════════════════════════════════════════════════════════
results = st.session_state.translation_results
errors = st.session_state.translation_errors

if results:
    st.divider()
    st.subheader(f"✅ 번역 완료: {len(results)}장")

    # 번역 이미지 미리보기 (2열)
    cols = st.columns(2)
    for i, (name, data) in enumerate(results):
        with cols[i % 2]:
            st.image(data, caption=name, use_container_width=True)

    # ZIP 다운로드
    st.divider()
    zip_bytes = create_zip(results)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    st.download_button(
        "📥 번역 이미지 ZIP 다운로드",
        data=zip_bytes,
        file_name=f"translated_images_{ts}.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )

if errors:
    with st.expander(f"❌ 실패한 이미지: {len(errors)}장", expanded=False):
        for name, err in errors:
            st.error(f"**{name}** — {err}")

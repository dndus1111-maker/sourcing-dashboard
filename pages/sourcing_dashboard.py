import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import html
import urllib.parse
from datetime import datetime

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
)
st.caption("셀러라이프 > 상품 소싱 > 카테고리 소싱에서 다운로드 받은 엑셀 파일을 업로드해주세요")

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

# ── 시즌(계절성) 컬럼 구성 ───────────────────────────────────────
#   계절성 있음 → "6,7,8월 (피크 7월)"   /   없음 → "-"
#   N열: 작년 최대검색 월(피크),  Q열: 계절성 월(잘 팔리는 달)  — 둘 다 선택적
_has_peak    = "작년 최대검색 월" in df_pass.columns
_has_smonths = "계절성 월" in df_pass.columns
_is_season   = df_pass["계절성"].astype(str).str.strip() == "있음"

# 피크월(N): 계절상품만 "6월" 형태로, 비계절은 "-"
def _peak_label(row):
    if str(row.get("계절성", "")).strip() != "있음":
        return "-"
    if _has_peak and pd.notna(row.get("작년 최대검색 월")):
        try:
            return f"{int(float(row['작년 최대검색 월']))}월"
        except (ValueError, TypeError):
            pass
    return "-"

# 시즌월(Q): 계절상품만 "5,6,7,8월" 형태로, 비계절은 "-"
def _smonth_label(row):
    if str(row.get("계절성", "")).strip() != "있음":
        return "-"
    if _has_smonths:
        q = str(row.get("계절성 월", "")).strip()
        if q and q not in ("없음", "nan"):
            return f"{q}월"
    return "-"

df_pass["피크월"] = df_pass.apply(_peak_label, axis=1)
df_pass["시즌월"] = df_pass.apply(_smonth_label, axis=1)

# 필터용 숫자 피크월 (계절상품만, 나머지는 NaN → 필터에서 제외)
if _has_peak:
    df_pass["_피크월"] = pd.to_numeric(df_pass["작년 최대검색 월"], errors="coerce").where(_is_season)
else:
    df_pass["_피크월"] = pd.NA

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
    # ── 계절상품만 보기 (서버측 필터) ────────────────────────────────
    season_only = st.checkbox("계절상품만 보기", value=False)

    view = df_pass.sort_values("최근 1개월 검색량", ascending=False).reset_index(drop=True)
    if season_only:
        view = view[view["계절성"].astype(str).str.strip() == "있음"].reset_index(drop=True)
        st.caption(f"계절상품만: {len(view)}개 (전체 통과 {n_pass:,}개 중)")

    def _row_html(r, i):
        kw = str(r["키워드"])
        kw_attr = html.escape(kw, quote=True)
        cp_url = ("https://www.coupang.com/np/search?q="
                  + urllib.parse.quote(kw) + "&channel=user")
        sk_url = ("https://sellochomes.co.kr/sellerlife/coupang-analysis-keyword/?keyword="
                  + urllib.parse.quote(kw))
        rocket = round(float(r["쿠팡 로켓배송비율"]) * 100, 1)
        overseas = round(float(r["쿠팡 해외배송비율"]) * 100, 1)

        # 카테고리: 1차 > 2차까지만 표시, 더 깊으면 클릭해서 펼치기
        cat = str(r["카테고리"])
        _parts = [p.strip() for p in cat.split(">") if p.strip()]
        if len(_parts) > 2:
            _short = " > ".join(_parts[:2])
            _cat_full = html.escape(cat, quote=True)
            cat_cell = (
                f'<td class="cat" data-full="{_cat_full}"><div class="cat-inner">'
                f'<span class="cat-text">{html.escape(_short)}</span>'
                f'<span class="cat-arrow" data-full="{_cat_full}" '
                f'data-short="{html.escape(_short, quote=True)}" '
                f'onclick="toggleCat(this)">▾</span>'
                f'</div></td>'
            )
        else:
            cat_cell = f'<td class="cat">{html.escape(cat)}</td>'

        return (
            f'<tr data-i="{i}">'
            f'<td class="kw">{html.escape(kw)}</td>'
            f'{cat_cell}'
            f'<td class="season c">{html.escape(str(r["피크월"]))}</td>'
            f'<td class="season">{html.escape(str(r["시즌월"]))}</td>'
            f'<td class="num">{int(r["최근 1개월 검색량"]):,}</td>'
            f'<td class="num">{rocket:.1f}%</td>'
            f'<td class="num">{overseas:.1f}%</td>'
            f'<td class="num">{int(r["쿠팡 해외배송 총리뷰수"]):,}</td>'
            '<td class="act">'
            f'<a class="btn btn-cp" href="{cp_url}" target="coupang_tab" '
            f'onclick="onCpClick(this,event)">🛒 쿠팡</a>'
            f'<a class="btn btn-sk" href="{sk_url}" target="_blank" rel="noopener" '
            f'data-kw="{kw_attr}" onclick="onSkClick(this)">📊 셀록홈즈</a>'
            '</td>'
            '<td class="c"><input type="checkbox" class="good"></td>'
            '<td class="c"><input type="checkbox" class="bad"></td>'
            '</tr>'
        )

    rows_html = "".join(_row_html(r, i) for i, (_, r) in enumerate(view.iterrows()))

    _html = """
<style>
  .rk-box { font-family: 'Segoe UI', 'Malgun Gothic', sans-serif; }
  .wrap { max-height: 560px; overflow: auto; border: 1px solid #e5e5e5; border-radius: 8px; }
  table.rk { border-collapse: collapse; width: 100%; font-size: 0.86rem; }
  table.rk th, table.rk td { border-bottom: 1px solid #eee; border-right: 1px solid #f0f0f0;
    padding: 7px 10px; text-align: left; white-space: nowrap; }
  table.rk th:last-child, table.rk td:last-child { border-right: none; }
  table.rk thead th { position: sticky; top: 0; background: #f4f5f7; z-index: 1;
    font-weight: 700; border-bottom: 2px solid #e0e0e0; vertical-align: middle; }
  table.rk tbody tr:hover { background: #fafbff; }
  .th-flex { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .sarr { color: #3b3bff; font-size: 0.72rem; }
  .fbtn { cursor: pointer; color: #999; font-size: 0.7rem; user-select: none; padding: 0 2px; }
  .fbtn:hover { color: #3b3bff; }
  .fbtn.active { color: #3b3bff; }
  .rowcount { margin-left: 12px; color: #666; font-size: 0.85rem; }
  .num { text-align: right; }
  .c { text-align: center; }
  .season { color: #555; font-size: 0.82rem; }
  .cat-inner { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .cat-arrow { color: #999; cursor: pointer; font-size: 0.72rem; user-select: none; }
  .cat-arrow:hover { color: #3b3bff; }
  .kw { font-weight: 600; }
  .fpanel { position: fixed; z-index: 1000; background: #fff; border: 1px solid #ccc;
    border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,.15); padding: 8px; width: 220px;
    font-size: 0.82rem; font-weight: 400; }
  .fp-sort { display: flex; gap: 6px; margin-bottom: 6px; }
  .fp-sort button, .fp-btns button { flex: 1; padding: 5px; border: 1px solid #ddd;
    background: #f7f7f9; border-radius: 5px; cursor: pointer; font-size: 0.8rem; }
  .fp-sort button:hover, .fp-btns button:hover { background: #ececff; }
  .fp-search { width: 100%; box-sizing: border-box; padding: 4px 6px; margin-bottom: 6px;
    border: 1px solid #ddd; border-radius: 5px; }
  .fp-all { display: block; padding: 3px 0; border-bottom: 1px solid #eee; margin-bottom: 4px; }
  .fp-list { max-height: 180px; overflow: auto; }
  .fp-item { display: block; padding: 2px 0; white-space: nowrap; cursor: pointer; }
  .fp-item:hover { background: #f5f5ff; }
  .fp-btns { display: flex; gap: 6px; margin-top: 8px; }
  .act { text-align: center; }
  .btn { display: inline-block; text-decoration: none; border-radius: 8px;
    padding: 6px 12px; font-size: 0.85rem; cursor: pointer; margin: 0 3px;
    transition: all 0.12s; }
  .btn-cp { background: #fff1f1; color: #e03131; border: 1px solid #ffc9c9; }
  .btn-cp:hover { background: #e03131; color: #fff; }
  .btn-sk { background: #f1f3ff; color: #3b3bff; border: 1px solid #c7c7ff; }
  .btn-sk:hover { background: #3b3bff; color: #fff; }
  .bar { margin: 10px 0 2px; }
  .dl { background: #111; color: #fff; border: none; border-radius: 8px;
    padding: 8px 16px; font-size: 0.9rem; cursor: pointer; }
  .toast { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);
    background: #222; color: #fff; padding: 8px 16px; border-radius: 8px;
    font-size: 0.9rem; opacity: 0; transition: opacity .2s; pointer-events: none; }
  .toast.show { opacity: .95; }
</style>
<div class="rk-box">
  <div class="wrap">
    <table class="rk">
      <thead><tr>
        <th data-col="0"><div class="th-flex"><span>키워드<span class="sarr"></span></span><span class="fbtn" data-col="0" onclick="openFilter(0,event)">▾</span></div></th>
        <th data-col="1"><div class="th-flex"><span>카테고리<span class="sarr"></span></span><span class="fbtn" data-col="1" onclick="openFilter(1,event)">▾</span></div></th>
        <th data-col="2"><div class="th-flex"><span>피크월<span class="sarr"></span></span><span class="fbtn" data-col="2" onclick="openFilter(2,event)">▾</span></div></th>
        <th data-col="3"><div class="th-flex"><span>시즌월<span class="sarr"></span></span><span class="fbtn" data-col="3" onclick="openFilter(3,event)">▾</span></div></th>
        <th data-col="4"><div class="th-flex"><span>검색량(1개월)<span class="sarr"></span></span><span class="fbtn" data-col="4" onclick="openFilter(4,event)">▾</span></div></th>
        <th data-col="5"><div class="th-flex"><span>로켓배송%<span class="sarr"></span></span><span class="fbtn" data-col="5" onclick="openFilter(5,event)">▾</span></div></th>
        <th data-col="6"><div class="th-flex"><span>해외배송%<span class="sarr"></span></span><span class="fbtn" data-col="6" onclick="openFilter(6,event)">▾</span></div></th>
        <th data-col="7"><div class="th-flex"><span>해외총리뷰<span class="sarr"></span></span><span class="fbtn" data-col="7" onclick="openFilter(7,event)">▾</span></div></th>
        <th>바로가기</th><th>👍 GOOD</th><th>👎 BAD</th>
      </tr></thead>
      <tbody>__ROWS__</tbody>
    </table>
  </div>
  <div class="bar">
    <button class="dl" onclick="exportCSV()">📥 마킹 포함 엑셀(CSV) 다운로드</button>
    <span id="rowcount" class="rowcount"></span>
  </div>
  <div id="toast" class="toast"></div>
</div>
<script>
  function copyToClip(kw) {
    try {
      var ta = document.createElement('textarea');
      ta.value = kw;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    } catch (e) {}
    try { if (navigator.clipboard) navigator.clipboard.writeText(kw); } catch (e) {}
  }
  function showToast(msg) {
    var t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(function(){ t.classList.remove('show'); }, 2000);
  }

  // 셀록홈즈/쿠팡을 각각 전용 창 하나에서 재사용 (창 핸들을 잡아 재이동 → 로그인 유지)
  var cpWin = null;
  // 셀록홈즈는 창을 재사용하면 쿠팡 윙 로그인이 풀리므로, 매번 새 탭에서 엽니다.
  function onSkClick(el) {
    copyToClip(el.getAttribute('data-kw'));
    showToast('셀록홈즈 여는 중: ' + el.getAttribute('data-kw') + ' (자동검색)');
    // 새 탭 열기는 앵커 기본 동작(target=_blank)에 맡깁니다.
  }
  // 쿠팡은 윙 로그인 이슈가 없으므로 전용 창 하나를 재사용합니다.
  function onCpClick(el, ev) {
    var url = el.getAttribute('href');
    if (cpWin && !cpWin.closed) {
      try { cpWin.location.href = url; cpWin.focus(); ev.preventDefault(); return; } catch (e) {}
    }
    var w = window.open(url, 'coupang_tab');
    if (w) { cpWin = w; ev.preventDefault(); }
  }
  function exportCSV() {
    var rows = document.querySelectorAll('table.rk tbody tr');
    var out = ['키워드,카테고리,피크월,시즌월,검색량,로켓배송%,해외배송%,해외총리뷰,GOOD,BAD'];
    rows.forEach(function(tr){
      if (tr.style.display === 'none') return;   // 필터로 숨긴 행 제외
      var td = tr.querySelectorAll('td');
      function cell(i){ return '"' + cellText(td[i]).replace(/"/g,'""') + '"'; }
      var good = tr.querySelector('.good').checked ? 'O' : '';
      var bad  = tr.querySelector('.bad').checked ? 'O' : '';
      out.push([cell(0),cell(1),cell(2),cell(3),cell(4),cell(5),cell(6),cell(7),
                '"'+good+'"','"'+bad+'"'].join(','));
    });
    var csv = '﻿' + out.join('\\r\\n');
    var blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'sourcing_result.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }

  // 카테고리 펼치기/접기 (1차>2차 ↔ 전체 경로)
  function toggleCat(el) {
    var textSpan = el.parentElement.querySelector('.cat-text');
    if (el.getAttribute('data-open') === '1') {
      textSpan.textContent = el.getAttribute('data-short');
      el.textContent = '▾'; el.setAttribute('data-open', '0');
    } else {
      textSpan.textContent = el.getAttribute('data-full');
      el.textContent = '▴'; el.setAttribute('data-open', '1');
    }
  }

  // 셀 텍스트 (카테고리는 잘려 있어도 data-full 전체 경로 기준으로 필터/정렬)
  function cellText(td) {
    return (td.getAttribute('data-full') || td.innerText || '');
  }

  // ── 엑셀식 필터/정렬 ──────────────────────────────────────────────
  function _num(s){
    var n = parseFloat((s || '').replace(/,/g, '').replace(/[^0-9.-]/g, ''));
    return isNaN(n) ? null : n;
  }
  var colFilters = {};   // col -> Set(허용 값)
  var panel = null;

  function distinctValues(col){
    var seen = {};
    document.querySelectorAll('table.rk tbody tr').forEach(function(tr){
      seen[cellText(tr.querySelectorAll('td')[col]).trim()] = true;
    });
    return Object.keys(seen).sort(function(a, b){
      var an = _num(a), bn = _num(b);
      if (an !== null && bn !== null) return an - bn;
      return a.localeCompare(b, 'ko');
    });
  }

  function closePanel(){ if (panel) { panel.remove(); panel = null; } }

  function openFilter(col, ev){
    ev.stopPropagation();
    closePanel();
    var vals = distinctValues(col);
    var allowed = colFilters[col];
    panel = document.createElement('div');
    panel.className = 'fpanel';

    var sortRow = document.createElement('div'); sortRow.className = 'fp-sort';
    var bAsc = document.createElement('button'); bAsc.textContent = '🔼 오름차순'; bAsc.onclick = function(){ doSort(col, 1); };
    var bDesc = document.createElement('button'); bDesc.textContent = '🔽 내림차순'; bDesc.onclick = function(){ doSort(col, -1); };
    sortRow.appendChild(bAsc); sortRow.appendChild(bDesc);
    panel.appendChild(sortRow);

    var search = document.createElement('input'); search.className = 'fp-search'; search.placeholder = '검색...';
    search.oninput = function(){
      var q = search.value.toLowerCase();
      panel.querySelectorAll('.fp-item').forEach(function(it){
        it.style.display = it.textContent.toLowerCase().indexOf(q) !== -1 ? '' : 'none';
      });
    };
    panel.appendChild(search);

    var allLbl = document.createElement('label'); allLbl.className = 'fp-all';
    var allBox = document.createElement('input'); allBox.type = 'checkbox'; allBox.checked = true;
    allBox.onchange = function(){
      panel.querySelectorAll('.fp-item').forEach(function(it){
        if (it.style.display !== 'none') it.querySelector('.fp-val').checked = allBox.checked;
      });
    };
    allLbl.appendChild(allBox); allLbl.appendChild(document.createTextNode(' (전체 선택)'));
    panel.appendChild(allLbl);

    var list = document.createElement('div'); list.className = 'fp-list';
    vals.forEach(function(v){
      var lbl = document.createElement('label'); lbl.className = 'fp-item';
      var cb = document.createElement('input'); cb.type = 'checkbox'; cb.className = 'fp-val'; cb.value = v;
      cb.checked = !allowed || allowed.has(v);
      if (!cb.checked) allBox.checked = false;
      lbl.appendChild(cb); lbl.appendChild(document.createTextNode(' ' + (v || '(빈값)')));
      list.appendChild(lbl);
    });
    panel.appendChild(list);

    var btns = document.createElement('div'); btns.className = 'fp-btns';
    var ok = document.createElement('button'); ok.textContent = '확인'; ok.onclick = function(){ applyColFilter(col); };
    var clr = document.createElement('button'); clr.textContent = '필터 해제'; clr.onclick = function(){ clearColFilter(col); };
    btns.appendChild(ok); btns.appendChild(clr);
    panel.appendChild(btns);

    document.body.appendChild(panel);
    var rect = ev.target.getBoundingClientRect();
    var left = Math.min(rect.left, window.innerWidth - 228);
    panel.style.left = Math.max(4, left) + 'px';
    panel.style.top = (rect.bottom + 2) + 'px';
    search.focus();
  }

  function applyColFilter(col){
    var boxes = panel.querySelectorAll('.fp-val');
    var checked = [];
    boxes.forEach(function(cb){ if (cb.checked) checked.push(cb.value); });
    if (checked.length === boxes.length) delete colFilters[col];
    else colFilters[col] = new Set(checked);
    markBtn(col); applyAllFilters(); closePanel();
  }
  function clearColFilter(col){ delete colFilters[col]; markBtn(col); applyAllFilters(); closePanel(); }

  function markBtn(col){
    var b = document.querySelector('.fbtn[data-col="' + col + '"]');
    if (b) b.className = 'fbtn' + (colFilters[col] ? ' active' : '');
  }

  function applyAllFilters(){
    var cols = Object.keys(colFilters).map(Number);
    var rows = document.querySelectorAll('table.rk tbody tr');
    var shown = 0;
    rows.forEach(function(tr){
      var td = tr.querySelectorAll('td');
      var ok = cols.every(function(c){ return colFilters[c].has(cellText(td[c]).trim()); });
      tr.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    var cnt = document.getElementById('rowcount'); if (cnt) cnt.textContent = shown + '개 표시';
  }

  function doSort(col, dir){
    var tbody = document.querySelector('table.rk tbody');
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    rows.sort(function(a, b){
      var av = cellText(a.querySelectorAll('td')[col]).trim();
      var bv = cellText(b.querySelectorAll('td')[col]).trim();
      var an = _num(av), bn = _num(bv), cmp;
      if (an !== null && bn !== null) cmp = an - bn;
      else cmp = av.localeCompare(bv, 'ko');
      return dir === 1 ? cmp : -cmp;
    });
    rows.forEach(function(r){ tbody.appendChild(r); });
    document.querySelectorAll('.sarr').forEach(function(s){ s.textContent = ''; });
    var sa = document.querySelector('th[data-col="' + col + '"] .sarr');
    if (sa) sa.textContent = dir === 1 ? ' ▲' : ' ▼';
    closePanel();
  }

  // 패널 바깥 클릭 시 닫기
  document.addEventListener('click', function(e){
    if (panel && !panel.contains(e.target) &&
        !(e.target.classList && e.target.classList.contains('fbtn'))) closePanel();
  });
</script>
""".replace("__ROWS__", rows_html)

    components.html(_html, height=680, scrolling=False)

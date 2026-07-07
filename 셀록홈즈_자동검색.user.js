// ==UserScript==
// @name         셀록홈즈 URL 자동검색
// @namespace    sourcing-dashboard
// @version      1.1
// @description  URL의 keyword 파라미터를 읽어 셀록홈즈 쿠팡 키워드분석을 자동으로 검색합니다. (구매대행 소싱 대시보드 연동)
// @match        https://sellochomes.co.kr/sellerlife/coupang-analysis-keyword*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
  'use strict';

  // URL 에서 keyword 파라미터 추출
  var kw = null;
  try { kw = new URLSearchParams(location.search).get('keyword'); } catch (e) {}
  if (!kw) return;  // 키워드 없으면 아무것도 안 함

  // React 호환 값 설정
  function setNativeValue(el, val) {
    var setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    setter.call(el, val);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function pressEnter(el) {
    el.focus();
    var opts = {
      key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
      bubbles: true, cancelable: true
    };
    el.dispatchEvent(new KeyboardEvent('keydown', opts));
    el.dispatchEvent(new KeyboardEvent('keypress', opts));
    el.dispatchEvent(new KeyboardEvent('keyup', opts));
  }

  // "분석 할 키워드를 입력해주세요" 팝업이 떠 있는지 (실패 신호)
  function popupOpen() {
    return document.body.innerText.indexOf('분석 할 키워드를 입력') !== -1;
  }

  // 팝업의 '확인' 버튼 클릭해서 닫기
  function closePopup() {
    var btn = Array.prototype.slice.call(document.querySelectorAll('button'))
      .filter(function (b) {
        return (b.innerText || '').trim() === '확인' && b.offsetParent !== null;
      })[0];
    if (btn) btn.click();
  }

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // 검색창이 나타날 때까지 대기 (SPA 로딩 고려)
  async function waitForInput() {
    var start = Date.now();
    while (Date.now() - start < 15000) {   // 최대 15초
      var el = document.querySelector('input.search-input');
      if (el && el.offsetParent !== null) return el;
      await wait(250);
    }
    return null;
  }

  (async function () {
    var input = await waitForInput();
    if (!input) return;

    await wait(800);  // 초기 하이드레이션 대기

    // 최대 4회 재시도 (로딩 타이밍이 어긋나 빈 검색이 되면 팝업 닫고 재시도)
    for (var i = 0; i < 4; i++) {
      if (popupOpen()) closePopup();
      setNativeValue(input, kw);
      await wait(600 + i * 400);   // 시도할수록 더 오래 대기
      pressEnter(input);
      await wait(1300);
      if (!popupOpen()) return;    // 팝업 없으면 성공 → 종료
      closePopup();
      await wait(400);
    }
  })();
})();

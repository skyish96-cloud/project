// login.js
// 역할: 로그인 화면 전담 컨트롤러 (Session 기반 로그인)

document.addEventListener('DOMContentLoaded', () => {
    const state = getInitialState();
    initLoginUI(state);
    bindLoginEvents(state);
    checkInputValidity(state);
    checkLoginStatus(state);   // 🔑 이미 로그인된 사용자 차단
});

/* =========================
   [1] 상태 생성
========================= */
function getInitialState() {
    return {
        onConfirm: null,
        isLoggedIn: false,
        userId: null,

        // DOM
        idInput: null,
        pwInput: null,
        submitBtn: null,
        loginForm: null,
        logoutBtn: null,
        errorMessage: null,

        modal: null,
        modalMsg: null,
        modalBtn: null
    };
}

/* =========================
   [2] UI 초기화
========================= */
function initLoginUI(state) {
    state.idInput = document.getElementById('userid');
    state.pwInput = document.getElementById('userpw');
    state.submitBtn = document.querySelector('.btn-submit');
    state.loginForm = document.querySelector('.login-form');
    state.logoutBtn = document.querySelector('.btn-logout');
    state.errorMessage = document.querySelector('.error-message');

    state.modal = document.getElementById('custom-alert');
    state.modalMsg = document.querySelector('.modal-message');
    state.modalBtn = document.getElementById('modal-ok-btn');
}

/* =========================
   [3] 로직 함수
========================= */

// 입력값에 따라 로그인 버튼 활성/비활성
function checkInputValidity(state) {
    if (!state.idInput || !state.pwInput || !state.submitBtn) return;

    state.submitBtn.disabled = !(
        state.idInput.value.length > 0 &&
        state.pwInput.value.length > 0
    );
}

// 공통 알림 모달
function showAlert(state, message, callback = null) {
    if (!state.modal || !state.modalMsg) return;

    state.modalMsg.textContent = message;
    state.modal.classList.add('show');
    state.onConfirm = callback;
}

// 로그인 payload
function buildLoginPayload(state) {
    return {
        user_id: state.idInput.value,
        user_pw: state.pwInput.value
    };
}

// 로그인 상태 UI 반영
function applyLoginState(state, userId) {
    state.isLoggedIn = Boolean(userId);
    state.userId = userId || null;
    document.body.classList.toggle('logged-in', state.isLoggedIn);
}

/* =========================
   [로그인 페이지 접근 가드]
   이미 로그인된 경우 → 메인으로 이동
========================= */
async function checkLoginStatus(state) {
    try {
        const res = await fetch('/auth/me', {
            credentials: 'include'
        });

        if (!res.ok) return;

        const data = await res.json();

        if (data.user_id) {
            // 이미 로그인된 상태
            window.location.replace('/');
        }
    } catch {
        console.warn('로그인 상태 확인 실패');
    }
}

// 로그아웃
async function logout(state) {
    try {
        await fetch('/logout', {
            method: 'POST',
            credentials: 'include'
        });
        location.reload();
    } catch {
        showAlert(state, '로그아웃 중 오류가 발생했습니다.');
    }
}

/* =========================
   [4] 이벤트 바인딩
========================= */
function bindLoginEvents(state) {

    // 입력 감지 & X 버튼
    document.querySelectorAll('.input-wrapper').forEach(wrapper => {
        const input = wrapper.querySelector('input');
        const btnClear = wrapper.querySelector('.btn-clear');
        if (!input || !btnClear) return;

        const updateClearBtn = () => {
            btnClear.classList.toggle('active', input.value.length > 0);
        };

        input.addEventListener('input', () => {
            updateClearBtn();
            checkInputValidity(state);
            state.errorMessage?.classList.remove('show');
        });

        btnClear.addEventListener('click', () => {
            input.value = '';
            input.focus();
            updateClearBtn();
            checkInputValidity(state);
        });
    });

    // 모달 확인 버튼
    state.modalBtn?.addEventListener('click', () => {
        state.modal.classList.remove('show');
        if (state.onConfirm) state.onConfirm();
        state.onConfirm = null;
    });

    // 로그인 요청
    if (state.loginForm && state.submitBtn) {
        state.loginForm.addEventListener('submit', async e => {
            e.preventDefault();
            if (state.submitBtn.disabled) return;

            try {
                const res = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify(buildLoginPayload(state))
                });

                const data = await res.json();

                // 로그인 실패
                if (!data.success) {
                    state.errorMessage?.classList.add('show');
                    state.idInput.value = '';
                    state.pwInput.value = '';
                    state.idInput.focus();
                    checkInputValidity(state);
                    return;
                }

                // 로그인 성공 → 세션 확인 후 이동
                showAlert(
                    state,
                    `${state.idInput.value}님 환영합니다!`,
                    async () => {
                        try {
                            sessionStorage.setItem("user_id", state.idInput.value);
                            const check = await fetch('/auth/me', {
                                credentials: 'include'
                            });

                            if (!check.ok) {
                                showAlert(state, '로그인 세션 확인에 실패했습니다.');
                                return;
                            }

                            window.location.href = '/';

                        } catch {
                            showAlert(state, '세션 확인 중 오류가 발생했습니다.');
                        }
                    }
                );

            } catch {
                showAlert(state, '서버와 통신 중 오류가 발생했습니다.');
            }
        });
    }

    // 로그아웃 버튼
    state.logoutBtn?.addEventListener('click', () => logout(state));
}
// signup.js
// 역할: 회원가입 화면 전체를 제어하는 컨트롤러
// - 상태 관리
// - 입력 검증
// - UX 처리
// - 서버 요청

document.addEventListener('DOMContentLoaded', () => {
    const state = getInitialState();   // 상태 객체 생성
    initSignupUI(state);               // DOM 요소 주입
    bindSignupEvents(state);           // 이벤트 바인딩
});

/* =========================
   [1] 상태 생성
   ========================= */
function getInitialState() {
    return {
        // 논리 상태
        isIdChecked: false,   // 아이디 중복확인 통과 여부
        onConfirm: null,      // 모달 확인 버튼 클릭 시 실행할 콜백

        // 입력 DOM
        idInput: null,
        pwInput: null,
        pwCheckInput: null,
        nameInput: null,
        birthInput: null,
        ageInput: null,
        emailInput: null,

        // 버튼 / 폼
        submitBtn: null,
        signupForm: null,
        checkIdBtn: null,

        // 안내 문구 DOM
        idHelper: null,
        pwHelper: null,
        emailHelper: null,

        // 모달 DOM
        modal: null,
        modalMsg: null,
        modalBtn: null
    };
}

/* =========================
   [2] DOM 바인딩
   ========================= */
// 실제 HTML 요소를 state 객체에 주입
function initSignupUI(state) {
    state.idInput = document.getElementById('userid');
    state.pwInput = document.getElementById('userpw');
    state.pwCheckInput = document.getElementById('userpw-check');
    state.nameInput = document.getElementById('username');
    state.birthInput = document.getElementById('birth');
    state.ageInput = document.getElementById('age');
    state.emailInput = document.getElementById('email');

    state.submitBtn = document.querySelector('.btn-submit');
    state.signupForm = document.querySelector('.signup-form');
    state.checkIdBtn = document.querySelector('.btn-check');

    state.idHelper = document.querySelector('.id-helper');
    state.pwHelper = document.querySelector('.pw-helper');
    state.emailHelper = document.querySelector('.email-helper');

    state.modal = document.getElementById('custom-alert');
    state.modalMsg = document.querySelector('.modal-message');
    state.modalBtn = document.getElementById('modal-ok-btn');
}

/* =========================
   [3] 로직 함수
   ========================= */
// 이메일 형식 검증
function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.(com|net|org|kr|co\.kr)$/i.test(email);
}

// 회원가입 버튼 활성/비활성 판단
function checkSignupValidity(state) {
    const {
        idInput, pwInput, pwCheckInput,
        nameInput, birthInput, ageInput, emailInput,
        isIdChecked, submitBtn
    } = state;

    // 모든 필드가 채워졌는지
    const isAllFilled =
        idInput.value.trim() &&
        pwInput.value &&
        pwCheckInput.value &&
        nameInput.value.trim() &&
        birthInput.value &&
        ageInput.value &&
        emailInput.value.trim();

    const isPwMatch = pwInput.value === pwCheckInput.value;      // 비밀번호 일치 여부
    const isEmailValid = isValidEmail(emailInput.value.trim());     // 이메일 형식 여부

    // 조건을 모두 만족해야 버튼 활성화
    submitBtn.disabled = !(isAllFilled && isPwMatch && isIdChecked && isEmailValid);
}
// 비밀번호 일치 안내 문구 처리
function checkPwMatch(state) {
    const { pwInput, pwCheckInput, pwHelper } = state;

    if (!pwInput.value || !pwCheckInput.value) {
        pwHelper.style.display = 'none';
        return;
    }

    const match = pwInput.value === pwCheckInput.value;
    pwHelper.textContent = match
        ? '비밀번호가 일치합니다.'
        : '비밀번호가 일치하지 않습니다.';
    pwHelper.style.color = match ? 'var(--orange)' : 'var(--blue)';
    pwHelper.style.display = 'block';
}
// 공통 알림 모달 표시 함수
function showAlert(state, message, callback = null) {
    state.modalMsg.textContent = message;
    state.modal.classList.add('show');
    state.onConfirm = callback;     // 확인 버튼 클릭 시 실행할 함수 저장
}

// 서버로 보낼 회원가입 payload 생성
function buildSignupPayload(state) {
    return {
        user_id: state.idInput.value.trim(),
        user_pw: state.pwInput.value,
        user_name: state.nameInput.value.trim(),
        user_birth: state.birthInput.value,
        user_age: Number(state.ageInput.value),
        user_gender:
            document.querySelector('input[name="gender"]:checked').value === 'female',
        user_email: state.emailInput.value.trim(),
        activation: true
    };
}

/* =========================
   [4] 이벤트 바인딩
   ========================= */
// 모든 사용자 상호작용 이벤트를 한 곳에서 관리
function bindSignupEvents(state) {

    // 입력 필드 감지 (X 버튼 + 실시간 검증)
    state.signupForm.querySelectorAll('.input-wrapper').forEach(wrapper => {
        const input = wrapper.querySelector('input');
        const clearBtn = wrapper.querySelector('.btn-clear');
        if (!input || !clearBtn) return;

        input.addEventListener('input', () => {
            clearBtn.classList.toggle('active', input.value.length > 0);

            // 비밀번호 관련 입력일 경우 일치 검사
            if (input === state.pwInput || input === state.pwCheckInput) {
                checkPwMatch(state);
            }

            // 아이디 수정 시 중복확인 무효화
            if (input === state.idInput) {
                state.isIdChecked = false;
                state.idHelper.style.display = 'none';
            }

            checkSignupValidity(state);
        });

        clearBtn.addEventListener('click', () => {
            input.value = '';
            clearBtn.classList.remove('active');
            checkSignupValidity(state);
        });
    });

    // 아이디 중복확인 버튼
    state.checkIdBtn.addEventListener('click', async () => {
        const userId = state.idInput.value.trim();
        if (!userId) return showAlert(state, '아이디를 입력해주세요.');

        try {
            const res = await fetch(`/users/check-id?user_id=${userId}`);
            const data = await res.json();

            if (data.exists) {
                state.idHelper.textContent = '이미 사용중인 아이디입니다.';
                state.idHelper.style.color = 'var(--blue)';
                state.isIdChecked = false;
            } else {
                state.idHelper.textContent = '사용 가능한 아이디입니다.';
                state.idHelper.style.color = 'var(--orange)';
                state.isIdChecked = true;
            }

            state.idHelper.style.display = 'block';
            checkSignupValidity(state);

        } catch {
            showAlert(state, '아이디 확인 중 오류가 발생했습니다.');
        }
    });

    // 이메일 검사
    state.emailInput.addEventListener('input', () => {
        const email = state.emailInput.value.trim();
        if (!email) {
            state.emailHelper.style.display = 'none';
            return;
        }

        const valid = isValidEmail(email);
        state.emailHelper.textContent = valid
            ? '올바른 이메일 형식입니다.'
            : '이메일 형식이 올바르지 않습니다.';
        state.emailHelper.style.color = valid ? 'var(--orange)' : 'var(--blue)';
        state.emailHelper.style.display = 'block';

        checkSignupValidity(state);
    });

    // 모달 확인
    state.modalBtn.addEventListener('click', () => {
        state.modal.classList.remove('show');
        if (state.onConfirm) state.onConfirm();
        state.onConfirm = null;
    });

    // 회원가입 제출
    state.signupForm.addEventListener('submit', async e => {
        e.preventDefault();
        if (state.submitBtn.disabled) return;

        try {
            const res = await fetch('/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(buildSignupPayload(state))
            });

            const data = await res.json();

            if (!data.success) return showAlert(state, '회원가입 실패');

            showAlert(
                state,
                '회원가입이 완료되었습니다!\n로그인 페이지로 이동합니다.',
                () => window.location.href = '/login'
            );

        } catch {
            showAlert(state, '서버 오류가 발생했습니다.');
        }
    });
}

// 1. 전역 상수 및 상태 변수
const EL = {
    questionList: () => document.getElementById('questionList'),
    nptiForm: () => document.getElementById('nptiForm'),
    modal: () => document.getElementById('testCompleteModal'),
    btnGoResult: () => document.getElementById('goToResult'),
    errorModal: () => document.getElementById('errorModal'),
    errorMessage: () => document.getElementById('errorMessage'),
    btnCloseError: () => document.getElementById('closeErrorModal')
};

const API = {
    GET_QUESTIONS: '/npti/q', // 백엔드 질문 db
    SAVE_RESULT: '/test' // 백엔드 설문 유저 응답 db
};

// 2. 메인 실행 DOMContentLoaded
document.addEventListener('DOMContentLoaded', async () => {

    // UI 초기화(질문 로드)를 먼저 시도하고, 그 결과로 로그인 여부를 판단
    const isLoaded = await initTestUI();

    // 질문 로드에 실패했다면 (서버에서 401을 줬다면) 함수를 종료
    // (리다이렉트는 fetchQuestions 함수 내부에서 처리함)
    if (!isLoaded) return;

    // 이벤트 리스너 등록
    EL.nptiForm()?.addEventListener('submit', handleTestSubmit); 

    // [확인] 버튼 클릭 시 이동 로직
    EL.btnGoResult()?.addEventListener('click', () => {
        location.href = "/result";
    });

    // 에러 모달 닫기 버튼
    EL.btnCloseError()?.addEventListener('click', () => {
        const modal = EL.errorModal();
        modal.classList.remove('show');
        setTimeout(() => { modal.style.display = 'none'; }, 300);
    });
    
});

// 3. 데이터 생성 및 헬퍼 함수
async function fetchQuestions() {
    try {
        const response = await fetch(API.GET_QUESTIONS);

        // 서버가 401(Unauthorized)을 반환하면 로그인 안 된 상태
        if (response.status === 401) {
            document.body.style.display = 'none';
            location.href = "/login"; // 로그인 페이지로 리다이렉트
            return null;
        }

        if (!response.ok) throw new Error('질문 로드 실패');
        return await response.json();
    } catch (err) {
        console.error('질문 데이터 로드 실패:', err);
        return null;
    }
}

/* 셔플(Shuffle) 함수: 질문 순서를 랜덤으로 섞음 */
function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

// 4. UI 컴포넌트 초기화 함수
async function initTestUI() {
    const form = EL.nptiForm();

    // 1. 데이터 로드 전 즉시 숨김
    if (form) {
        form.style.display = "none";
    }

    const data = await fetchQuestions();
    if (!data) return false;

    // 질문 렌더링
    const shuffled = shuffleArray([...data]);
    renderQuestionCards(shuffled);

    // 데이터 로드 및 렌더링이 완료된 후 폼을 짜잔! 하고 보여줌
    if (form) {
        form.style.display = "block";
    }

    return true;
}

function renderQuestionCards(questions) {
    const listArea = EL.questionList();
    if (!listArea) return;

    // 질문 번호를 제외하고 q_text 등 DB 필드 기반 렌더링
    const html = questions.map((q, index) => `
        <div class="q-card">
            <p class="q-title">Q${index + 1}. ${q.question_text}</p>
            <div class="options-group">
                <span class="option-label">매우 그렇지 않다</span>
                ${[1, 2, 3, 4, 5].map(num => `
                    <div class="option-item">
                        <input type="radio" 
                               name="${q.question_id}" 
                               value="${num}" 
                               required
                               data-axis="${q.npti_axis}"
                               data-ratio="${q.question_ratio}">
                        <span class="option-num">${num}</span>
                    </div>
                `).join('')}
                <span class="option-label">매우 그렇다</span>
            </div>
        </div>
    `).join('');

    listArea.innerHTML = html;
}

/* 5. NPTI 개인화 로직 섹션 */
async function handleTestSubmit(e) {
    e.preventDefault(); // 기본 제출 동작 막기
    console.log("=== 제출 프로세스 시작 (최신 버전) ==="); // 이 문구가 콘솔에 떠야 합니다.

    // 제출 버튼 비활성화 (여러 번 클릭 방지)
    const submitBtn = e.target.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    const formData = new FormData(EL.nptiForm());

    let answers = {}; // 개별 문항 점수 (db_user_answers용)
    let finalScores = { length: 0, article: 0, information: 0, view: 0 }; // 합산 점수 (user_npti용)

    // 데이터 수집 및 계산 로직
    for (let [qId, value] of formData.entries()) {
        const score = parseInt(value);
        answers[qId] = score;

        const input = document.querySelector(`input[name="${qId}"]:checked`);
        if (!input) continue;

        const axis = input.dataset.axis;
        const ratio = parseFloat(input.dataset.ratio) || 0; // 가중치가 없으면 0 처리

        // 정규화 (0, 0.25, 0.5, 0.75, 1) 적용
        const normalized = (score - 1) / 4;

        const targetAxis = (axis === 'info') ? 'information' : axis;

        if (finalScores.hasOwnProperty(targetAxis)) {
            finalScores[targetAxis] += (normalized * ratio);
        }
    }
    
    // 100분율 변환 및 반올림 (DB가 INT이므로 정수로 변환)
    Object.keys(finalScores).forEach(key => {
        // 1. 먼저 가중치가 곱해진 순수 백분율 값을 구합니다. (예: 0.496 * 100 = 49.6)
        let rawPercent = finalScores[key] * 100;
        let finalValue;

        // 2. [반올림 전 보정] 50점 인근의 데드존(Dead Zone) 처리
        if (rawPercent >= 49 && rawPercent < 50) {
            // 49.0 ~ 49.999... 구간은 무조건 49로 고정
            finalValue = 49;
        }
        else if (rawPercent >= 50 && rawPercent < 51) {
            // 50.0 ~ 50.999... 구간은 무조건 51로 고정
            finalValue = 51;
        }
        else {
            // 그 외의 구간(예: 48.2, 52.7 등)은 일반적인 반올림 처리
            finalValue = Math.round(rawPercent);
        }

        // 3. 최종 정수 값 저장 (DB가 INT형이므로 정수 보장)
        finalScores[key] = finalValue;
    });

    console.log("보정된 정수 점수 (50점 없음):", finalScores);

    // 최종 NPTI 타입 결정 4글자 코드 생성
    const type = [
        finalScores.length > 50 ? 'S' : 'L',
        finalScores.article > 50 ? 'T' : 'C',
        finalScores.information > 50 ? 'F' : 'I',
        finalScores.view > 50 ? 'N' : 'P'
    ].join('');
    const nptiScores = {
     long: 100 - finalScores.length, short:finalScores.length,
     content: 100 - finalScores.article, tale: finalScores.article,
     fact : finalScores.information , insight : 100 - finalScores.information,
     positive: 100 - finalScores.view, negative: finalScores.view}

     console.log("최종 npti 점수 ; ", nptiScores)

    // 백엔드 /npti/save 호출
    const payload = {
        npti_result: type,
        scores: nptiScores,
        answers: answers
    };

    // 저장 요청
    const result = await saveNPTIResult(payload);
    if (result.success) {
        console.log("DB 저장 성공");
        showModal(); // 완료 모달 표시
    } else {
        console.error("저장 에러:", result.message);
        showErrorModal(`결과 저장 중 오류가 발생했습니다.
        다시 시도해주세요`);
        if (submitBtn) submitBtn.disabled = false;
    }
}

// 6. 이벤트 핸들러 및 모달 관리
async function saveNPTIResult(payload) {
    try {
        const response = await fetch('/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        return await response.json();
    } catch (err) {
        console.error('통신 실패:', err);
        return false;
    }
}

function showModal() {
    const modal = EL.modal();
    if (modal) {
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('show'), 10);
    }
}

// 에러 모달 표시 함수
function showErrorModal(msg) {
    const modal = EL.errorModal();
    const msgEl = EL.errorMessage();
    if (modal && msgEl) {
        msgEl.innerText = msg; // 에러 메시지 삽입
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('show'), 10);
    }
}
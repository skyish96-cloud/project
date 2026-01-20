// 1. 전역 상수 및 상태 변수
const EL = {
    // userName: () => document.getElementById('userName'),
    userId: () => document.getElementById('userId'),
    nptiCode: () => document.getElementById('nptiCode'),
    nptiName: () => document.getElementById('nptiName'),
    resultSummary: () => document.getElementById('resultSummary'),
    goCurationBtn: () => document.getElementById('goCurationBtn'),
    chartItems: () => document.querySelectorAll('.chart-item')
};

// 2. 메인 실행 (DOMContentLoaded)
document.addEventListener('DOMContentLoaded', async () => {
    // [보안] 로그인 및 결과 데이터 존재 여부 확인 
    const isReady = await initResultPage();

    if (isReady) {
        // [이벤트] 버튼 클릭 핸들러 등록
        EL.goCurationBtn()?.addEventListener('click', handleGoMain);
    }
});

// 3. 데이터 생성 및 헬퍼 함수 (서버 통신)
async function fetchResultData() {
    try {
        const response = await fetch('/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error('서버 응답 오류');

        return await response.json();
    } catch (err) {
        console.error("[Data Error] 결과 데이터를 가져오지 못했습니다:", err);
        return null;
    }
}

// 4. UI 컴포넌트 초기화 및 렌더링
async function initResultPage() {
    const res = await fetchResultData();

    // 1. 서버 응답 자체를 먼저 확인 (튕기지 않게 주석 유지)
    console.log("서버 응답 데이터(res):", res);

    if (!res) {
        console.error("서버 응답이 null입니다. 백엔드 터미널 로그를 확인하세요.");
        return false; // 리다이렉트 안 하고 여기서 멈춤
    }
    
    globalSession.isLoggedIn = Boolean(res.isLoggedIn);
    globalSession.hasNPTI = Boolean(res.hasNPTI);

    console.log("로그인 상태:", globalSession.isLoggedIn);
    console.log("진단 결과 유무:", globalSession.hasNPTI);
    
    // 3. 성공 케이스
    if (globalSession.isLoggedIn && globalSession.hasNPTI) {
        if (res.user_npti) {
            globalSession.nptiResult = res.user_npti.npti_code;
            renderResultToUI(res);
            return true;
        }
    }

    // 3. 성공 케이스
    if (globalSession.isLoggedIn && globalSession.hasNPTI) {
        if (res.user_npti) {
            globalSession.nptiResult = res.user_npti.npti_code;
            renderResultToUI(res);
            return true;
        }
    }

    // 2. 로그인은 되어 있으나 진단 결과가 없는 경우
    if (globalSession.isLoggedIn && !globalSession.hasNPTI) {
        console.warn("진단 결과가 없습니다. 테스트 페이지로 이동합니다.");
        location.href = "/test";
        return false;
    }

    // 3. 비로그인 상태이거나 기타 예외 상황
    console.error("로그인 상태가 아닙니다. 로그인 페이지로 이동합니다.");
    location.href = "/login";
    return false;
}

/* UI 렌더링 전담 함수 
- 데이터를 화면에 뿌려주는 로직을 별도로 분리
*/
function renderResultToUI(res) {
    const { user_npti, code_info, all_types, user_id, user_name } = res;

    // A. 텍스트 정보 삽입 (db_npti_code 데이터 연결)
    // if (EL.userName()) EL.userName().textContent = user_name || "독자";
    if (EL.userId()) EL.userId().textContent = user_id;
    if (EL.nptiCode()) EL.nptiCode().textContent = user_npti.npti_code;
    if (EL.nptiName()) EL.nptiName().textContent = code_info.type_nick;

    console.log("최신 데이터 업데이트 시간:", user_npti.updated_at)

    // B. 요약 설명 줄바꿈 처리
    if (EL.resultSummary()) {
        const rawText = code_info.type_de || "";
        const formattedText = rawText.split('.')
            .map(s => s.trim())
            .filter(Boolean)
            .join('.<br>');

        const finalHtml = formattedText + (rawText.endsWith('.') ? '.' : '');
        EL.resultSummary().innerHTML = `<p>${finalHtml}</p>`;
    }

    // C. 차트 렌더링 로직 (점수 매핑 없이 다이렉트 접근)
    const axisKeys = [['length','short'], ['article','tale'], ['info','fact'], ['view','negative']];

    axisKeys.forEach((key, idx) => {
        // 해당 축(axis)에 맞는 그룹 쌍(예: S/L) 필터링
        const groupPair = all_types.filter(t => t.npti_group === key[0]);

        // key 이름을 활용해 점수에 동적으로 접근 (예: user_npti['length_score'])
        const scorePercentage = user_npti[`${key[1]}_score`];

        console.log(`[연결 확인] 축: ${key[0]}, 데이터 개수: ${groupPair.length}, 점수: ${scorePercentage}`);

        if (groupPair.length >= 2 && scorePercentage !== undefined) {
            renderChartItem(key, groupPair, scorePercentage, idx);
        } else {
            console.warn(`${key} 축의 매핑 데이터가 부족합니다.`);
        }
    });
}

/* 개별 차트 바 및 라벨 렌더링 */
function renderChartItem(key, pair, score, idx) {
    const container = EL.chartItems()[idx];
    if (!container) return;

    // pair[0]: 왼쪽(0 성향 - Long, Content, Insight, Positive)
    // pair[1]: 오른쪽(1 성향 - Short, Tale, Fact, Negative)
    const leftArchetypes = ['L', 'C', 'I', 'P'];
    let leftType = pair.find(t => leftArchetypes.includes(t.npti_type));
    let rightType = pair.find(t => !leftArchetypes.includes(t.npti_type));

    if (!leftType || !rightType) {
        leftType = pair[0];
        rightType = pair[1];
    }

    // 1. score가 문자열로 들어올 경우를 대비해 확실하게 숫자로 변환
    const numericScore = Number(score);

    // 가중치 합산 점수(score)는 질문 설계상 '오른쪽 타입'의 강도
    // 예: Q1-1~3에 '매우 그렇다'를 할수록 Short(오른쪽) 점수가 높아짐
    const rightVal = isNaN(numericScore) ? 0 : Math.round(numericScore); // 오른쪽 성향 수치
    const leftVal = 100 - rightVal;     // 왼쪽 성향 수치
    const maxVal = Math.min(Math.max(Math.max(leftVal, rightVal), 0), 100); // 바(bar)의 너비

    // A. [즉시 실행] 글씨와 숫자는 즉시 반영
    // score가 70일 때: rightVal=70, leftVal=30, maxVal=70

    // 텍스트 및 숫자 삽입 로직
    const labelL = container.querySelector('.label-left');
    const labelR = container.querySelector('.label-right');

    if (labelL) {
        // % 기호와 숫자가 누락되지 않도록 주의
        labelL.innerHTML = `${leftType.npti_kor} <b style="color:var(--orange)">${leftVal}%</b>`;
    }
    if (labelR) {
        labelR.innerHTML = `<b style="color:var(--orange)">${rightVal}%</b> ${rightType.npti_kor}`;
    }

    // 알파벳 매핑
    const charL = container.querySelector('.char-left');
    const charR = container.querySelector('.char-right');
    if (charL) {
        charL.style.transition = "none";
        charL.textContent = leftType.npti_type; // 'L', 'C', 'I', 'P' 등 
        charL.style.color = leftVal >= rightVal ? "var(--orange)" : "#ccc"; // 왼쪽이 크거나 같으면 강조색, 작으면 회색
    }
    if (charR) {
        charR.style.transition = "none";
        charR.textContent = rightType.npti_type; // 'S', 'T', 'F', 'N' 등
        charR.style.color = rightVal > leftVal ? "var(--orange)" : "#ccc"; // 오른쪽이 더 크면 강조색, 작거나 같으면 회색
    }

    // B. [애니메이션] 막대기만 서서히 차오름
    const bar = container.querySelector('.progress-bar.orange-bar');
    if (bar) {
        bar.style.transition = "none";
        bar.style.width = "0%";

        if (leftVal >= rightVal) {
            bar.style.left = "0"; bar.style.right = "auto";
        } else {
            bar.style.left = "auto"; bar.style.right = "0";
        }

        void bar.offsetWidth;

        setTimeout(() => {
            bar.style.transition = "width 1.2s ease-out";
            bar.style.width = maxVal + "%";
        }, 100);
    }
}

// 5. 이벤트 핸들러 및 페이지 이동
function handleGoMain() {
    // 메인 페이지(큐레이션)로 이동 전 상태 기록
    location.href = "/";
}
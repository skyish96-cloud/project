/* =================================================================
   🚀 메인 실행부 (Control Tower)
================================================================= */

document.addEventListener('DOMContentLoaded', async () => {
    // 1. UI 기본 세팅
    setupInterface();

    // 2. 데이터 호출
    const user = await fetchProfile();
    const npti = await fetchNptiResult();

    // 3. 유저 정보 렌더링
    if (user) {
        renderUserFields(user);
    } else {
        window.location.replace("/login");
        return;
    }

    // 4. NPTI 결과 렌더링 및 업데이트 로직
    if (npti) {
        renderNptiContent(npti);

        const updateBtn = document.getElementById('goCurationBtn');
        const tooltip = document.getElementById('nptiUpdateTooltip');

        const latest_update_time = npti.updated_at;

        if (latest_update_time) {
            let now = new Date();
            let lastUpdateDate = new Date(latest_update_time.replace(" ","T"));
            let diff_update_time = now - lastUpdateDate;
            const hours24InMs = 24*60*60*1000

            if (diff_update_time < hours24InMs) {
                applyUpdateLock();
                if (tooltip) tooltip.style.display = 'none';
                return;
            }
        }

        // 업데이트 버튼 클릭 이벤트 연결
        if (updateBtn) {
            updateBtn.onclick = () => runUpdateSimulation();

            // 툴팁 이벤트
            updateBtn.addEventListener('mouseenter', () => {
                if (!updateBtn.disabled && tooltip) tooltip.style.display = 'block';
            });
            updateBtn.addEventListener('mouseleave', () => {
                if (tooltip) tooltip.style.display = 'none';
            });
        }
    } else {
        showEmptyNpti();
    }
});


/* =================================================================
   1. 데이터 통신부 (Pure Data Fetching)
================================================================= */

async function fetchProfile() {
    try {
        const res = await fetch('/mypage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        if (res.status === 401) return null;
        return res.ok ? await res.json() : null;
    } catch (e) {
        console.error("프로필 로드 실패:", e);
        return null;
    }
}

async function fetchNptiResult() {
    try {
        const res = await fetch('/result', { method: 'POST' });
        if (!res.ok) return null;

        const data = await res.json();
        if (!data.hasNPTI && !data.hasResult) return null;

        return {
            ...data.user_npti,
            type_nick: data.code_info.type_nick || data.code_info.information_type,
            type_de: data.code_info.type_de,
            info_score: data.user_npti.information_score
        };
    } catch (e) {
        console.error("NPTI 로드 실패:", e);
        return null;
    }
}

/* =================================================================
   2. UI 렌더링부 (Pure Rendering)
================================================================= */

function renderUserFields(user) {
    const displayId = document.getElementById('displayId');
    if (displayId) displayId.innerText = `@${user.userId}`;

    const fields = {
        'dbName': user.name,
        'dbEmail': user.email,
        'dbBirth': user.birth,
        'dbAge': user.age,
        'dbGender': user.gender
    };

    Object.entries(fields).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.value = val || "";
    });
}

function renderNptiContent(npti) {
    const resSection = document.getElementById('nptiResultSection');
    if (resSection) resSection.style.display = 'block';

    document.getElementById('resUserName').innerText = npti.user_id;
    document.getElementById('nptiCode').innerText = npti.npti_code;
    document.getElementById('nptiName').innerText = npti.type_nick;
    const rawText = npti.type_de;
    const fomattedText = rawText.split('.').map(s => s.trim()).filter(Boolean).join('.<br/>');
    document.getElementById('resultSummary').innerHTML = fomattedText;
    renderBarChart('barLength', npti.long_score, "L", "S", 'track-Length');
    renderBarChart('barArticle', npti.content_score, 'C', 'T', 'track-Article');
    renderBarChart('barInfo', npti.insight_score, "I", "F", 'track-Info');
    renderBarChart('barView', npti.positive_score, 'P', 'N', 'track-View');
}

function renderBarChart(id, scoreLeft, charLeft, charRight, trackId) {
    const scoreRight = 100 - scoreLeft;
    const bar = document.getElementById(id);
    const track = document.getElementById(trackId);
    if (!bar || !track) return;

    document.getElementById(`score-${charLeft}`).innerText = `${scoreLeft}%`;
    document.getElementById(`score-${charRight}`).innerText = `${scoreRight}%`;

    const sLeft = document.getElementById(`score-${charLeft}`);
    const sRight = document.getElementById(`score-${charRight}`);
    const cLeft = document.getElementById(`char-${charLeft}`);
    const cRight = document.getElementById(`char-${charRight}`);

    [cLeft, cRight].forEach(el => el?.classList.remove('char-highlight'));

    const isLeftHigher = scoreLeft >= scoreRight;
    track.style.justifyContent = isLeftHigher ? 'flex-start' : 'flex-end';

    if (isLeftHigher) {
        cLeft?.classList.add('char-highlight');
        if(sLeft) sLeft.style.color = 'var(--orange)';
        if(sRight) sRight.style.color = '';
    } else {
        cRight?.classList.add('char-highlight');
        if(sRight) sRight.style.color = 'var(--orange)';
        if(sLeft) sLeft.style.color = '';
    }

    bar.style.transition = 'none';
    bar.style.width = '0%';
    setTimeout(() => {
        bar.style.transition = 'width 3s cubic-bezier(0.1, 0.5, 0.5, 1)';
        bar.style.width = (isLeftHigher ? scoreLeft : scoreRight) + '%';
        bar.className = isLeftHigher ? 'progress-bar orange-bar' : 'progress-bar orange-bar-right';
    }, 50);
}

function showEmptyNpti() {
    const resSection = document.getElementById('nptiResultSection');
    if (resSection) resSection.style.display = 'none';

    const updateBtn = document.getElementById('goCurationBtn');
    if (updateBtn) {
        updateBtn.innerText = "NPTI 진단 시작하기";
        updateBtn.onclick = () => location.href = "/test";
        document.getElementById('nptiUpdateTooltip')?.remove();
    }
}

/* =================================================================
   3. 기능 설정부 (Event Listeners & Action Logic)
================================================================= */

function setupInterface() {
    const dotsMenu = document.getElementById('dotsMenu');
    const withdrawModal = document.getElementById('withdrawModal');

    // 점 세개 메뉴 토글
    document.querySelector('.btn-dots')?.addEventListener('click', (e) => {
        e.stopPropagation();
        dotsMenu.classList.toggle('show');
    });

    // 탈퇴 모달 열기
    document.getElementById('btnShowWithdraw')?.addEventListener('click', (e) => {
        e.preventDefault();
        withdrawModal.classList.add('show');
        dotsMenu.classList.remove('show');
    });

    // 탈퇴 모달 닫기
    document.getElementById('closeWithdraw')?.addEventListener('click', () => {
        withdrawModal.classList.remove('show');
    });

    // [중요] 회원 탈퇴 확정 실행
    document.getElementById('confirmWithdraw')?.addEventListener('click', async () => {
        try {
            const res = await fetch('/users/withdraw', { method: 'POST' });
            if (res.ok) window.location.href = "/";
            else alert("탈퇴 처리 중 오류가 발생했습니다.");
        } catch (e) {
            console.error("탈퇴 요청 실패:", e);
        }
    });

    // 외부 클릭 시 메뉴 닫기
    document.addEventListener('click', () => dotsMenu?.classList.remove('show'));
}

function applyUpdateLock() {
    const updateBtn = document.getElementById('goCurationBtn');
    if (!updateBtn) return;
    updateBtn.disabled = true;
    updateBtn.innerText = "업데이트 완료 (24시간 후 가능)";
    updateBtn.style.backgroundColor = "#ccc";
    updateBtn.style.borderColor = "#ccc";
    updateBtn.style.cursor = "not-allowed";
}

// [중요] 업데이트 시뮬레이션 실행 함수
async function runUpdateSimulation() {
    const updateBtn = document.getElementById('goCurationBtn');
    const tooltip = document.getElementById('nptiUpdateTooltip');
    const summary = document.getElementById('resultSummary');
    let newNPTI = null;

    //fetch - get. /update_user_npti
    try {
        const res = await fetch('/update_user_npti', {
            method: 'get'
        });
        if (res.ok) {
            newNPTI = await res.json();
        } else {
            console.error("업데이트 실패");
            return;
        }

    } catch (e) {
        console.error("통신 에러", e)
        return;
    }
    if (newNPTI) {
        // 화면의 NPTI 코드 텍스트도 업데이트

        // id, scoreLeft, charLeft, charRight, trackId
        // long, content, insight, positive
        renderNptiContent(newNPTI);

        applyUpdateLock();

        // 2. 성공 메시지 표시
        if (summary) {
            const msg = document.createElement('p');
            msg.style.cssText = "color:var(--orange); font-weight:800; margin-top:15px;";
            msg.innerHTML = "✨ 최근 유저 행동 데이터를 기반으로 NPTI가 업데이트되었습니다!";
            summary.appendChild(msg);
            setTimeout(() => msg.remove(), 300000);
        }
    }
}


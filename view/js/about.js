// ui설계서와 db와 내용 통일
// 데이터를 window 객체에 등록하여 main.js에서 접근 가능하게 합니다.
window.NPTI_DB = {
    intro: {
        title: "NPTI 란?",
        content: `<b>NPTI(News Personality Type Indicator)</b>는<br>뉴스 읽는 방식과 정보 선호도를 분석해<br><span class="highlight-orange">나에게 맞는 뉴스 경험</span>을 제안하는 서비스입니다.`
    },
    criteria: [
        { title: "Length", left: "S - 짧게 핵심만", right: "L - 깊이 있는 분석" },
        { title: "Style", left: "C - 정보 중심", right: "T - 이야기 중심" },
        { title: "Information", left: "F - 사실 전달 중심", right: "I - 분석·해석 중심" },
        { title: "Viewpoint", left: "P - 우호·긍정적", right: "N - 비판·문제제기" }
    ],
    guides: [
        { code: "LTFP", name: "\"따뜻한 장문 탐독가\"", desc: "장문의 이야기 속에서 '따뜻한 사실'을 찾는 독자.", pref: "스토리 중심으로 몰입할 수 있는 희망적인 기사 선호." },
        { code: "LTFN", name: "\"현실 통찰 독서가\"", desc: "현실을 통찰하는 긴 스토리를 통해 사회의 어두운 본질을 깊이 파고드는 독자.", pref: "문제의 구조와 원인을 차분히 짚는 기사 선호." },
        { code: "LTIP", name: "\"낙관적 사유가\"", desc: "낙관적 서사를 통해 해석과 교훈을 얻는 독자.", pref: "긴 서술 속에서 의미와 통찰을 발견할 수 있는 기사 선호." },
        { code: "LTIN", name: "\"구조 해부 사상가\"", desc: "구조적 해부와 분석을 통해 복잡한 문제를 이해하려는 독자.", pref: "이야기 속 원인과 구조를 깊게 분석하는 기사 선호." },
        { code: "LCFP", name: "\"밝은 정보 협독가\"", desc: "풍부한 정보와 맥악을 통해 사실을 넓게 이해하려는 독자.", pref: "장문의 정보 기사에서 차분한 설명을 제공하는 기사 선호." },
        { code: "LCFN", name: "\"팩트 정밀 감시자\"", desc: "팩트와 근거를 통해 사회 문제의 구조를 파악하려는 독자.", pref: "정보 위주의 장문 기사로 맥락을 설명하는 기사 선호." },
        { code: "LCIP", name: "\"장문 전망 분석가\"", desc: "정보를 기반으로 전망과 해석에 관심을 두는 독자.", pref: "장문의 기사에서 미래 흐름과 의미를 제시하는 기사 선호." },
        { code: "LCIN", name: "\"리스크 구조 분석가\"", desc: "리스크와 논점을 구조적으로 분석하려는 독자.", pref: "문제를 냉정하게 해부하는 정보 중심 기사 선호." },
        { code: "STFP", name: "\"힐링 스토리 리더\"", desc: "짧은 이야기 속에서 따뜻한 사실을 찾는 독자.", pref: "힘들 때 읽으면 가볍게 기분이 좋아지는 기사 선호." },
        { code: "STFN", name: "\"팩트 현실주의자\"", desc: "짧은 스트레이트 기사로 현실의 불편한 진실을 확인하려는 독자.", pref: "팩트 위주의 간결한 기사 선호." },
        { code: "STIP", name: "\"핵심 낙관주의자\"", desc: "짧은 기사에서도 의미와 교훈을 얻고 싶어 하는 독자.", pref: "핵심 메시지가 분명한 기사 선호." },
        { code: "STIN", name: "\"비판적 통찰 추적자\"", desc: "짧고 단단한 기사로 문제를 빠르게 파악하려는 독자.", pref: "비판적 관점이 명확한 기사 선호." },
        { code: "SCFP", name: "\"속도형 정보 소비자\"", desc: "빠르게 정보를 확인하며 긍정적인 흐름을 알고 싶어 하는 독자.", pref: "속도감 있는 정보 기사 중 밝은 톤의 기사 선호." },
        { code: "SCFN", name: "\"경계심 강한 체커\"", desc: "빠른 정보 속에서 사건의 구조와 맥락을 파악하려는 독자.", pref: "경제·사회 이슈를 간결하게 정리한 기사 선호." },
        { code: "SCIP", name: "\"빠른 인사이트 수집가\"", desc: "짧은 기사라도 인사이트를 얻고 싶어 하는 독자.", pref: "핵심 해석이 분명한 요약형 기사 선호." },
        { code: "SCIN", name: "\"리스크 감지 전문가\"", desc: "위험 요소와 문제점을 빠르게 감지하려는 독자.", pref: "리스크와 원인을 분석한 간결한 기사 선호." }
    ]
};

// about.html 페이지 자체에서도 내용이 보여야 하므로 실행
document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('aboutRoot');
    if (root) {
        renderNPTI(root);
    }
});

// 화면을 그리는 공통 함수
function renderNPTI(target) {
    const db = window.NPTI_DB;
    if (!target || !db) return;
    
    target.innerHTML = `
        <section class="about-section">
            <h2 class="section-title">${db.intro.title}</h2>
            <p class="intro-text">${db.intro.content}</p>
        </section>
        <section class="about-section">
            <h2 class="section-title">NPTI 4가지 분류 기준</h2>
            <div class="criteria-grid">
                ${db.criteria.map(item => `
                    <div class="criteria-card">
                        <h3>${item.title}</h3>
                        <p>${item.left}<br><span class="vs-text">VS</span><br>${item.right}</p>
                    </div>
                `).join('')}
            </div>
        </section>
        <section class="about-section">
            <h2 class="section-title">NPTI 16가지 성향 가이드</h2>
            <div class="guide-grid">
                ${db.guides.map(guide => `
                    <div class="guide-card">
                        <div class="guide-code">${guide.code}</div>
                        <span class="guide-nickname">${guide.name}</span>
                        <p class="guide-desc">${guide.desc}</p>
                        <p class="guide-preference">${guide.pref}</p>
                    </div>
                `).join('')}
            </div>
        </section>
    `;
}
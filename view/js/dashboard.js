let globalStatsData = null;
let globalArticlesData = null;
let chartInstances = {};

// Chart.js 전역 설정 (폰트 등)
Chart.defaults.font.family = "'Pretendard', sans-serif";
Chart.defaults.color = '#666';

// 색상 팔레트
const COLORS = {
    orange: '#FF6B00',
    blue: '#0057FF',
    red: '#FF6384',
    green: '#4BC0C0',
    purple: '#9966FF',
    grey: '#C9CBCF',
    yellow: '#FFCE56',
    brown:'#A52A2A',
    mix: ['#FF6384', // Red
        '#0057FF', // Blue
        '#FFCE56', // Yellow
        '#4BC0C0', // Teal
        '#9966FF', // Purple
        '#FF6B00', // Orange
        '#2E8B57', // SeaGreen
        '#FF4500', // OrangeRed
        '#4682B4', // SteelBlue
        '#D2691E', // Chocolate
        '#00CED1', // DarkTurquoise
        '#DC143C', // Crimson
        '#556B2F', // DarkOliveGreen
        '#000080', // Navy
        '#FFD700', // Gold
        '#8A2BE2', // BlueViolet
        '#A52A2A', // Brown
        '#00FA9A', // MediumSpringGreen
        '#C71585', // MediumVioletRed
        '#708090', // SlateGray
        '#1E90FF', // DodgerBlue
        '#ADFF2F', // GreenYellow
        '#FF1493', // DeepPink
        '#4B0082', // Indigo
        '#20B2AA', // LightSeaGreen
        '#808000', // Olive
        '#B03060', // Maroon
        '#3CB44B', // Green
        '#F032E6'  // Magenta
    ]
};

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

async function initDashboard() {
    try {
        const res = await fetch('/members_statistics');
        globalStatsData = await res.json();
        console.log({"statsdata" : globalStatsData});
    } catch (e) {
        console.error("회원 통계 데이터 로드 실패", e);
        return;
    }

    // 1. 관리자 권한 체크
    const sessionStr = sessionStorage.getItem('admin_session');
    if (!sessionStr) {
        sessionStorage.setItem('admin_session', JSON.stringify({ id: 'admin', role: 'admin' }));
    }

    // 2. 탭 네비게이션 설정
    setupTabNavigation();

    // 3. 초기 화면 렌더링
    renderContent('stats');

    try {
        const resStats = await fetch('/articles_statistics');
        globalArticlesData = await resStats.json();
        console.log({"articlesdata" : globalArticlesData});
    } catch (e) {
        console.error("기사 통계 데이터 로드 실패", e);
    }
}

function setupTabNavigation() {
    const tabs = document.querySelectorAll('.nav-tabs a');
    tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            e.preventDefault();
            const category = tab.dataset.category;
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            renderContent(category);
        });
    });
}

function renderContent(category) {
    const contentArea = document.getElementById('adminContentArea');
    if (!contentArea) return;

    if (category === 'stats') {
        contentArea.innerHTML = `
            <div class="layout-wrapper animate-fade-in">
                ${createSection("NPTI별 회원 분포", "npti_main", "npti_sub", false)}
                ${createSection("NPTI 4가지 분류별 회원분포", "metrics_main", "metrics_sub", false)}
            </div>`;
    }
    else if (category === 'articles') {
        contentArea.innerHTML = `
            <div class="layout-wrapper animate-fade-in">
                ${createSection("카테고리별 수집기사", "news_categories", "", true)}
                ${createSection("NPTI별 수집기사", "npti_sub", "metrics_short", true)}
            </div>`;
    }
    else {
        contentArea.innerHTML = renderNoData();
    }

    if (globalStatsData) {
        drawChartsForCategory(category);
    }
}

function renderNoData() {
    return `<div class="no-data-container"><div class="no-data-box"><p>데이터가 없습니다.</p></div></div>`;
}

function createSection(title, leftField, rightField, isToggleLeft = false) {
    const isSingle = (rightField === "" || rightField === null);
    const leftCanvasId = `canvas-${leftField || 'left-' + title.replace(/\s/g, '')}`;

    const leftBoxHtml = `
        <div class="box-container half">
            ${createBoxHeader(title, leftField, isToggleLeft, leftCanvasId)}
            <div class="chart-container">
                <canvas id="${leftCanvasId}"></canvas>
            </div>
        </div>`;

    const rightCanvasId = `canvas-${rightField || 'right-' + title.replace(/\s/g, '')}`;
    let rightBoxHtml = "";
    if (isSingle) {
        rightBoxHtml = `<div class="box-container half" style="visibility: hidden;"></div>`;
    } else {
        rightBoxHtml = `
            <div class="box-container half">
                ${createBoxHeader(title, rightField, !isToggleLeft, rightCanvasId)}
                <div class="chart-container">
                    <canvas id="${rightCanvasId}"></canvas>
                </div>
            </div>`;
    }

    return `
        <div class="section-outer-header">
            <h3 class="section-main-title">${title}</h3>
            <span class="box-timestamp">${globalStatsData.time_now}</span>
        </div>
        <div class="layout-section">
            <div class="layout-row">
                ${leftBoxHtml}
                ${rightBoxHtml}
            </div>
        </div>`;
}

const options = {
    'npti_main': ['NPTI', '나이', '성별'],
    'npti_sub': ['STFP', 'STFN', 'STIP', 'STIN', 'SCFP', 'SCFN', 'SCIP', 'SCIN', 'LTFP', 'LTFN', 'LTIP', 'LTIN', 'LCFP', 'LCFN', 'LCIP', 'LCIN'],
    'metrics_main' : ['속성별 분포'],
    'metrics_sub': ['Short', 'Long', 'Content', 'Tale', 'Fact', 'Insight', 'Positive', 'Negative'],
    'news_categories': ['정치', '경제', '사회', '생활/문화', 'IT/과학', '세계', '스포츠', '연예', '지역'],
    'metrics_short': ['S/L', 'C/T', 'F/I', 'P/N']
};

function createBoxHeader(title, fieldType, hasToggle, targetCanvasId) {
    const leftContent = hasToggle
        ? `<div class="toggle-group" data-title="${title}">
                <button type="button" class="btn-toggle active">일별</button>
                <button type="button" class="btn-toggle">주별</button>
                <button type="button" class="btn-toggle">월별</button>
           </div>`
        : "";

    const checkboxFields = ['npti_main', 'npti_sub', 'metrics_sub', 'news_categories', 'metrics_short'];
    let rightContent = "";

    if (fieldType && options[fieldType] && fieldType !== 'metrics_main') {
        if (checkboxFields.includes(fieldType)) {
            const isSingleSelect = (fieldType === 'npti_main');
            const inputType = isSingleSelect ? 'radio' : 'checkbox';
            const inputName = isSingleSelect ? `${fieldType}_group` : '';

            const dropdownItems = options[fieldType].map((opt, index) => {
                const isChecked = isSingleSelect ? (index === 0 ? 'checked' : '') : 'checked';
                return `
                    <label class="checkbox-label">
                        <input type="${inputType}" ${inputName ? `name="${inputName}"` : ""} ${isChecked} onclick="event.stopPropagation()">
                        <span class="checkbox-text">${opt}</span>
                    </label>
                `;
            }).join('');

            const btnText = isSingleSelect ? 'NPTI' : '필드';
            rightContent = `
                <div class="custom-dropdown" data-title="${title}" data-target="${targetCanvasId}" onclick="this.classList.toggle('active')">
                    <button class="dropdown-btn" onclick="event.stopPropagation(); this.parentElement.classList.toggle('active')">
                        ${btnText} <span class="arrow">▼</span>
                    </button>
                    <div class="dropdown-menu" onclick="event.stopPropagation()">
                        <div class="checkbox-list">${dropdownItems}</div>
                    </div>
                </div>`;
        } else {
            rightContent = `
                <select class="box-select" data-title="${title}" data-target="${targetCanvasId}">
                    ${options[fieldType].map(opt => `<option>${opt}</option>`).join('')}
                </select>`;
        }
    }

    return `<div class="box-header"><div class="header-left">${leftContent}</div><div class="header-right">${rightContent}</div></div>`;
}

function handleUIEvents(e) {
    const toggleBtn = e.target.closest('.btn-toggle');
    if (e.type === 'click' && toggleBtn) {
        const toggleGroup = toggleBtn.parentElement;
        toggleGroup.querySelectorAll('.btn-toggle').forEach(btn => btn.classList.remove('active'));
        toggleBtn.classList.add('active');

        const boxTitle = toggleGroup.getAttribute('data-title') || "시간 단위";
        const targetId = toggleGroup.getAttribute('data-target');
        const selectedValue = toggleBtn.innerText;
        updateSpecificChart(boxTitle, selectedValue, true, targetId);
        return;
    }

    if (e.type === 'change' && e.target.classList.contains('box-select')) {
        const select = e.target;
        const boxTitle = select.getAttribute('data-title') || "필드 선택";
        console.log("[" + boxTitle + "] 적용된 필드:", [select.value]);
        return;
    }

    if (e.type === 'click') {
        const activeDropdowns = document.querySelectorAll('.custom-dropdown.active');
        activeDropdowns.forEach(dropdown => {
            if (!dropdown.contains(e.target)) {
                let checkedInputs = dropdown.querySelectorAll('input[type="checkbox"]:checked, input[type="radio"]:checked');

                if (checkedInputs.length === 0) {
                    const allInputs = dropdown.querySelectorAll('input[type="checkbox"]');
                    allInputs.forEach(input => { input.checked = true; });
                    checkedInputs = dropdown.querySelectorAll('input[type="checkbox"]:checked');
                }

                const selectedValues = Array.from(checkedInputs).map(input => {
                    const textSpan = input.parentElement.querySelector('.checkbox-text');
                    return textSpan ? textSpan.innerText : input.value;
                });

                const boxTitle = dropdown.getAttribute('data-title') || "선택 필드";
                const targetId = dropdown.getAttribute('data-target');
                const btn = dropdown.querySelector('.dropdown-btn');
                const isRadio = dropdown.querySelector('input[type="radio"]');

                if (btn && isRadio && selectedValues.length > 0) {
                    btn.innerHTML = `${selectedValues[0]} <span class="arrow">▼</span>`;
                }

                console.log("[" + boxTitle + "] 적용된 필드:", selectedValues);
                updateSpecificChart(boxTitle, selectedValues, false, targetId);
                dropdown.classList.remove('active');
            }
        });
    }
}

function drawChartsForCategory(category) {
    if (!globalStatsData) return;

    if (category === 'stats') {
        createPieChart('canvas-npti_main', globalStatsData.result1_npti_code, 'npti_code');
        createLineChartNPTI('canvas-npti_sub', globalStatsData.result2_day);
        createStackedBarChart('canvas-metrics_main', globalStatsData.result3_npti_type);
        createLineChartType('canvas-metrics_sub', globalStatsData.result4_day);
    }

    if (!globalArticlesData) return;

    if (category === 'articles') {
        createLineChartCategory('canvas-news_categories', globalArticlesData.result1_day);
        createLineChartNPTI('canvas-npti_sub', globalArticlesData.result2_day, 'article_count');
        createAttributeStackedBar('canvas-metrics_short', globalArticlesData.result3_day);
    }
}

// ==========================================================
// [Chart 1] Pie Chart (% 변환)
// ==========================================================
function createPieChart(canvasId, data, labelKey) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    ctx.parentNode.style.height = '320px';

    const existingChart = Chart.getChart(ctx);
    if (existingChart) existingChart.destroy();
    if (chartInstances[canvasId]) delete chartInstances[canvasId];

    if (!data || data.length === 0) {
        console.warn(`[${canvasId}] 데이터가 없습니다.`);
        return;
    }

    // 1. 라벨 변환
    const labels = data.map(item => {
        const rawValue = item[labelKey];
        if (labelKey === 'user_gender') {
            if (rawValue === 0 || rawValue === '0') return '남성';
            if (rawValue === 1 || rawValue === '1') return '여성';
            return '알 수 없음';
        }
        return rawValue;
    });

    // 2. 값(Count) -> 백분율(Percentage) 변환
    const counts = data.map(item => item.count);
    const totalCount = counts.reduce((sum, val) => sum + val, 0);

    // totalCount가 0이면 0으로 처리, 아니면 퍼센트 계산 (소수점 1자리)
    const percentages = counts.map(val => totalCount === 0 ? 0 : parseFloat(((val / totalCount) * 100).toFixed(1)));

    chartInstances[canvasId] = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: percentages, // 퍼센트 데이터 사용
                backgroundColor: COLORS.mix.slice(0, labels.length),
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { boxWidth: 12 } },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.label || '';
                            if (label) label += ': ';
                            // 툴팁에도 % 붙여서 표시
                            label += context.parsed + '%';
                            return label;
                        }
                    }
                }
            }
        }
    });
}

// ==========================================================
// [Chart 2] Stacked Bar Chart (Y축 0~100% 고정)
// ==========================================================
function createStackedBarChart(canvasId, data) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    ctx.parentNode.style.height = '320px';

    const existingChart = Chart.getChart(ctx);
    if (existingChart) existingChart.destroy();

    const labels = ['에너지 (L vs S)', '인식 (C vs T)', '판단 (I vs F)', '계획 (P vs N)'];

    // 각 속성값
    const L = data.L_count || 0;
    const S = data.S_count || 0;
    const C = data.C_count || 0;
    const T = data.T_count || 0;
    const I = data.I_count || 0;
    const F = data.F_count || 0;
    const P = data.P_count || 0;
    const N = data.N_count || 0;

    // 쌍별 합계 (Total)
    const totalLS = L + S || 1; // 0나누기 방지
    const totalCT = C + T || 1;
    const totalIF = I + F || 1;
    const totalPN = P + N || 1;

    // 퍼센트 변환 함수
    const toPct = (val, total) => parseFloat(((val / total) * 100).toFixed(1));

    const dataLeft = [toPct(L, totalLS), toPct(C, totalCT), toPct(I, totalIF), toPct(P, totalPN)];
    const dataRight = [toPct(S, totalLS), toPct(T, totalCT), toPct(F, totalIF), toPct(N, totalPN)];

    chartInstances[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                { label: 'Left Type (L,C,I,P)', data: dataLeft, backgroundColor: COLORS.blue },
                { label: 'Right Type (S,T,F,N)', data: dataRight, backgroundColor: COLORS.orange }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { stacked: true },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    min: 0,
                    max: 100, // Y축 최대 100% 고정
                    ticks: {
                        callback: function(value) { return value + "%" } // 눈금에 % 표시
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.parsed.y + '%';
                        }
                    }
                }
            }
        }
    });
}

// ==========================================================
// [Chart 3] Line Chart (NPTI Code별)
// ==========================================================
function createLineChartNPTI(canvasId, rawData, countKey = 'user_count') {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    ctx.parentNode.style.height = '320px';

    const existingChart = Chart.getChart(ctx);
    if (existingChart) existingChart.destroy();

    const dates = [...new Set(rawData.map(item => item.date_period))];
    const chartLabels = dates.map(dateStr => {
        if (dateStr.includes('\n')) {
            return dateStr.split('\n');
        }
        return dateStr;
    });
    const codes = [...new Set(rawData.map(item => item.npti_code))];

    const datasets = codes.map((code, idx) => {
        const dataPoints = dates.map(date => {
            const found = rawData.find(r => r.date_period === date && r.npti_code === code);
            const count = found ? found[countKey] : 0;
            // (해당 코드 수 / 그날 전체 사용자 수) * 100
            return count;
        });

        return {
            label: code,
            data: dataPoints,
            borderColor: COLORS.mix[idx % COLORS.mix.length],
            tension: 0.3,
            fill: false,
            clip: false,
            pointRadius: 4,
            pointHoverRadius: 6
        };
    });

    chartInstances[canvasId] = new Chart(ctx, {
        type: 'line',
        data: { labels: chartLabels, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip : {
                    callbacks : {
                        label : function (context) {
                            if (countKey === 'user_count') {
                                return context.dataset.label + ": " + context.parsed.y + '명';
                                }
                            if (countKey === 'article_count') {
                                return context.dataset.label + ": " + context.parsed.y + '건';
                                }
                        }
                    }
                }
            },
            layout: {
                padding: {top: 20, right: 10, left: 10}
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                }
            }
        }
    });
}

// ==========================================================
// [Chart 4] Line Chart (Type 속성별)
// ==========================================================
function createLineChartType(canvasId, rawData) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    ctx.parentNode.style.height = '320px';

    const existingChart = Chart.getChart(ctx);
    if (existingChart) existingChart.destroy();

    const dates = rawData.map(d => d.date_period);
    const chartLabels = dates.map(dateStr => {
        if (dateStr.includes('\n')) {
            return dateStr.split('\n');
        }
        return dateStr;
    });

    const types = [
        { key: 'L_count', label: 'Long', color: COLORS.orange },
        { key: 'S_count', label: 'Short', color: COLORS.grey },
        { key: 'C_count', label: 'Content', color: COLORS.blue },
        { key: 'T_count', label: 'Tale', color: COLORS.purple },
        { key: 'I_count', label: 'Insight', color: COLORS.green },
        { key: 'F_count', label: 'Fact', color: COLORS.red },
        { key: 'P_count', label: 'Positive', color: COLORS.yellow },
        { key: 'N_count', label: 'Negative', color: COLORS.brown }
    ];

    const datasets = types.map(t => ({
        label: t.label,
        data: rawData.map(row => row[t.key] || 0),
        borderColor: t.color,
        tension: 0.3,
        hidden: false,
        clip: false,
        pointRadius: 4,
        pointHoverRadius: 6
    }));

    chartInstances[canvasId] = new Chart(ctx, {
        type: 'line',
        data: { labels: chartLabels, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            layout: {
                padding: {top:20, right: 10, left :10}
            },
            plugins: {
                tooltip : {
                    callbacks : {
                        label : function(context) {return context.dataset.label + ': '+context.parsed.y+'건';}
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision : 0
                    }
                }
            }
        }
    });
}

// ==========================================================
// [Chart 5] Grouped Stacked Bar Chart (기사 속성 4종 쌍 비교)
// ==========================================================
function createAttributeStackedBar(canvasId, rawData) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    ctx.parentNode.style.height = '320px';

    const existingChart = Chart.getChart(ctx);
    if (existingChart) existingChart.destroy();
    if (chartInstances[canvasId]) delete chartInstances[canvasId];

    // 1. 라벨(날짜) 처리
    const dates = rawData.map(d => d.date_period);
    const chartLabels = dates.map(dateStr => {
        return dateStr.includes('\n') ? dateStr.split('\n') : dateStr;
    });

    // 2. 데이터셋 구성 (4개의 Stack 그룹 정의)
    // 각 쌍(Pair)은 같은 'stack' ID를 공유해야 위아래로 쌓입니다.
    const datasets = [
        // Group 1: Length (L vs S)
        {
            label: 'Long',
            data: rawData.map(d => d.L_count),
            backgroundColor: COLORS.orange,
            stack: 'Stack_Length'
        },
        {
            label: 'Short',
            data: rawData.map(d => d.S_count),
            backgroundColor: '#FFD580', // 연한 오렌지 (L과 대비)
            stack: 'Stack_Length'
        },

        // Group 2: Type (C vs T)
        {
            label: 'Content',
            data: rawData.map(d => d.C_count),
            backgroundColor: COLORS.blue,
            stack: 'Stack_Type'
        },
        {
            label: 'Tale',
            data: rawData.map(d => d.T_count),
            backgroundColor: '#ADD8E6', // 연한 블루
            stack: 'Stack_Type'
        },

        // Group 3: Info (I vs F)
        {
            label: 'Insight',
            data: rawData.map(d => d.I_count),
            backgroundColor: COLORS.green,
            stack: 'Stack_Info'
        },
        {
            label: 'Fact',
            data: rawData.map(d => d.F_count),
            backgroundColor: '#90EE90', // 연한 그린
            stack: 'Stack_Info'
        },

        // Group 4: View (P vs N)
        {
            label: 'Positive',
            data: rawData.map(d => d.P_count),
            backgroundColor: COLORS.purple,
            stack: 'Stack_View'
        },
        {
            label: 'Negative',
            data: rawData.map(d => d.N_count),
            backgroundColor: '#E6E6FA', // 연한 퍼플
            stack: 'Stack_View'
        }
    ];

    chartInstances[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: chartLabels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.parsed.y}건`;
                        }
                    }
                },
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, padding: 15 }
                }
            },
            scales: {
                x: {
                    stacked: true, // X축 스택 활성화
                    grid: { display: false }
                },
                y: {
                    stacked: true, // Y축 스택 활성화
                    beginAtZero: true,
                    ticks: { precision: 0 }
                }
            }
        }
    });
}

// ==========================================================
// [Chart 6] Line Chart (Category 별)
// ==========================================================
function createLineChartCategory(canvasId, rawData) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    ctx.parentNode.style.height = '320px';

    const existingChart = Chart.getChart(ctx);
    if (existingChart) existingChart.destroy();

    // 1. 날짜(X축) 추출
    const dates = [...new Set(rawData.map(item => item.date_period))];
    const chartLabels = dates.map(dateStr => {
        return dateStr.includes('\n') ? dateStr.split('\n') : dateStr;
    });

    // 2. 카테고리(범례) 추출
    const categories = [...new Set(rawData.map(item => item.category))];

    // 3. 데이터셋 구성
    const datasets = categories.map((cat, idx) => {
        const dataPoints = dates.map(date => {
            const found = rawData.find(r => r.date_period === date && r.category === cat);
            return found ? found.count : 0;
        });

        return {
            label: cat,
            data: dataPoints,
            // 색상은 기존 mix 팔레트 활용
            borderColor: COLORS.mix[idx % COLORS.mix.length],
            tension: 0.3,
            fill: false,
            pointRadius: 3,
            pointHoverRadius: 5
        };
    });

    chartInstances[canvasId] = new Chart(ctx, {
        type: 'line',
        data: { labels: chartLabels, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false }, // 상단 범례 숨김 (외부 필터 사용 시)
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ": " + context.parsed.y + '건';
                        }
                    }
                }
            },
            layout: {
                padding: { top: 20, right: 10, left: 10 }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { precision: 0 }
                }
            }
        }
    });
}


// [수정] 4번째 인자 targetCanvasId 추가 (기존 함수 전체 덮어쓰기)
function updateSpecificChart(boxTitle, changedValue, isToggleEvent = false, targetCanvasId = null) {
    if (!globalStatsData && !globalArticlesData) return;

    // [Helper 함수] 차트 재생성 후, 현재 UI(드롭다운)에 체크된 필터값을 읽어 다시 적용하는 함수
    const reapplyFilter = (tId) => {
        if (!tId) return;
        // 해당 캔버스 ID를 타겟으로 하는 드롭다운 찾기
        const dropdown = document.querySelector(`.custom-dropdown[data-target="${tId}"]`);
        if (!dropdown) return;

        // 체크된 항목들 가져오기
        const checkedInputs = dropdown.querySelectorAll('input[type="checkbox"]:checked, input[type="radio"]:checked');

        // 체크된 텍스트 추출
        const selectedValues = Array.from(checkedInputs).map(input => {
             const textSpan = input.parentElement.querySelector('.checkbox-text');
             return textSpan ? textSpan.innerText : input.value;
        });

        // CASE 2 로직(필터링)을 재귀 호출하여 적용 (isToggleEvent = false)
        updateSpecificChart(boxTitle, selectedValues, false, tId);
    };

    // ============================================================
    // CASE 1: 시간 단위 변경 (Toggle) -> 섹션 내 모든 차트 데이터 교체
    // ============================================================
    if (isToggleEvent) {
        // 1. [Stats] NPTI별 회원 분포 & 변화
        if (boxTitle === 'NPTI별 회원 분포') {
            const canvasId = 'canvas-npti_sub';
            let newData = null;
            if (changedValue === '일별') newData = globalStatsData.result2_day;
            else if (changedValue === '주별') newData = globalStatsData.result2_week;
            else if (changedValue === '월별') newData = globalStatsData.result2_month;

            if (newData) {
                createLineChartNPTI(canvasId, newData);
                reapplyFilter(canvasId); // [추가] 필터 복구
            }
        }
        // 2. [Stats] 4가지 분류별 변화
        else if (boxTitle === 'NPTI 4가지 분류별 회원분포') {
            const canvasId = 'canvas-metrics_sub';
            let newData = null;
            if (changedValue === '일별') newData = globalStatsData.result4_day;
            else if (changedValue === '주별') newData = globalStatsData.result4_week;
            else if (changedValue === '월별') newData = globalStatsData.result4_month;

            if (newData) {
                createLineChartType(canvasId, newData);
                reapplyFilter(canvasId); // [추가] 필터 복구
            }
        }
        // 3. [Articles] 카테고리별 수집기사
        else if (boxTitle === '카테고리별 수집기사') {
             const canvasId = 'canvas-news_categories';
             let newData = null;
             if (changedValue === '일별') newData = globalArticlesData.result1_day;
             else if (changedValue === '주별') newData = globalArticlesData.result1_week;
             else if (changedValue === '월별') newData = globalArticlesData.result1_month;

             if (newData) {
                 createLineChartCategory(canvasId, newData);
                 reapplyFilter(canvasId); // [추가] 필터 복구
             }
        }
        // 4. [Articles] NPTI별 수집기사 (왼쪽/오른쪽 둘 다 바뀜)
        else if (boxTitle === 'NPTI별 수집기사') {
            const leftId = 'canvas-npti_sub';
            const rightId = 'canvas-metrics_short';

            let leftData = null, rightData = null;
            if (changedValue === '일별') {
                leftData = globalArticlesData.result2_day;
                rightData = globalArticlesData.result3_day;
            } else if (changedValue === '주별') {
                leftData = globalArticlesData.result2_week;
                rightData = globalArticlesData.result3_week;
            } else if (changedValue === '월별') {
                leftData = globalArticlesData.result2_month;
                rightData = globalArticlesData.result3_month;
            }

            if (leftData) {
                createLineChartNPTI(leftId, leftData, 'article_count');
                reapplyFilter(leftId); // [추가] 왼쪽 차트 필터 복구
            }
            if (rightData) {
                createAttributeStackedBar(rightId, rightData);
                reapplyFilter(rightId); // [추가] 오른쪽 차트 필터 복구
            }
        }
        return;
    }

    // ============================================================
    // CASE 2: 필터 변경 (Dropdown) -> 특정 Canvas만 업데이트 (targetCanvasId 사용)
    // ============================================================
    if (!targetCanvasId) return;

    // Pie Chart 예외 처리 (데이터 다시 그리기)
    if (boxTitle === 'NPTI별 회원 분포' && targetCanvasId === 'canvas-npti_main') {
        let newData = null, labelKey = '';
        if (changedValue[0] === 'NPTI') { newData = globalStatsData.result1_npti_code; labelKey = 'npti_code'; }
        else if (changedValue[0] === '나이') { newData = globalStatsData.result1_age; labelKey = 'age_group'; }
        else if (changedValue[0] === '성별') { newData = globalStatsData.result1_gender; labelKey = 'user_gender'; }
        if (newData) createPieChart(targetCanvasId, newData, labelKey);
        return;
    }

    const chart = chartInstances[targetCanvasId];
    if (chart) {
        // Stacked Bar Chart 특수 로직 (Stack 그룹 필터링)
        if (targetCanvasId === 'canvas-metrics_short') {
            chart.data.datasets.forEach(ds => {
                let isVisible = false;
                if (ds.stack === 'Stack_Length' && changedValue.includes('S/L')) isVisible = true;
                if (ds.stack === 'Stack_Type' && changedValue.includes('C/T')) isVisible = true;
                if (ds.stack === 'Stack_Info' && changedValue.includes('F/I')) isVisible = true;
                if (ds.stack === 'Stack_View' && changedValue.includes('P/N')) isVisible = true;
                if (changedValue.length === 0) isVisible = true;
                ds.hidden = !isVisible;
            });
        }
        // 일반 Line/Bar Chart 로직 (Label 필터링)
        else {
            chart.data.datasets.forEach(ds => {
                ds.hidden = !changedValue.includes(ds.label);
            });
        }
        chart.update();
    }
}

// 이벤트 리스너 등록
['click', 'change'].forEach(evt => window.addEventListener(evt, handleUIEvents));
document.addEventListener('DOMContentLoaded', () => {
    ///* 1. 가상 DB 데이터 주입 및 요소 캐싱 */
    // const userData = {
    //     userId: "admin",
    //     name: "홍길동",
    //     birth: "1999-09-16",
    //     age: 28,
    //     gender: "male",
    //     email: "Honggildong@email.com"
    // };

    // 이메일 유효성 검사 함수 추가
    const isValidEmail = (email) => {
        const pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return pattern.test(email);
    };

    // FastAPI 서버 주소 (배포 환경에 따라 수정)
    //const API_BASE_URL = "http://127.0.0.1:8000";
    const btnSave = document.querySelector('.btn-save');
    btnSave.disabled = true;

    // 필수 입력 요소들 캐싱
    const fields = {
        username: document.getElementById('username'),
        currentPw: document.getElementById('current-pw'),
        newPw: document.getElementById('new-pw'),
        newPwCheck: document.getElementById('new-pw-check'),
        birth: document.getElementById('birth'),
        age: document.getElementById('age'),
        email: document.getElementById('email')
    };
    
    const currentMsg = document.getElementById('current-pw-msg');
    const newMsg = document.getElementById('new-pw-msg');
    const checkMsg = document.getElementById('new-pw-check-msg');
    const editForm = document.querySelector('.edit-form');
    const editModal = document.getElementById('editModal');
    const confirmEdit = document.getElementById('confirmEdit');
    const closeEdit = document.getElementById('closeEdit')
    const emailMsg = document.getElementById('email-msg');

    let isPasswordVerified = false;
    let currentEncryptedPw = '';
    let originalEncryptedPw = '';

    // 유저 데이터 가져오기(세션)(GET)
    const loadUserData = async () => {
        const loggedInUserId = sessionStorage.getItem("user_id");
        //console.log("세션에서 가져온 id :", loggedInUserId);

        if (!loggedInUserId) {
            alert("로그인 세션이 만료되었습니다. 다시 로그인해주세요.");
            window.location.href = "/login";
            return;
        }
        try {
            // FastAPI 엔드포인트에 userId를 쿼리 파라미터나 경로로 전달
            const response = await fetch(`/users/profile?user_id=${loggedInUserId}`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (response.ok) {
                const userData = await response.json();
                console.log("서버 응답 데이터:", userData);
                
                // 데이터 주입
                const handleEl = document.getElementById('displayHandle');
                if (handleEl) {
                    // 백엔드에서 userId로 주는지 user_id로 주는지 확인 필요
                    handleEl.innerText = `@${userData.userId || userData.user_id}`;
                }
                
                fields.username.value = userData.name || "";
                fields.birth.value = userData.birth || "";
                fields.age.value = userData.age || "";
                fields.email.value = userData.email || "";
                originalEncryptedPw = userData.user_pw || "";
                
                // 성별 라디오 버튼
                const genderRadios = document.getElementsByName('gender');
                let genderValue = '';
                if (userData.gender === "남자") genderValue = "male";
                else if (userData.gender === "여자") genderValue = "female";
                for (let radio of genderRadios) {
                    if (radio.value === genderValue) {
                        radio.checked = true;
                        break;
                    }
                } 

                updateButtonState();
            } else {
                const error = await response.json();
                alert(`데이터 로드 실패: ${error.detail}`);
            }
        } catch (error) {
            console.error("FastAPI 통신 오류:", error);
        }
    };

    // 모든 필드 검사 및 버튼 활성화 함수
    const updateButtonState = () => {

        // 비밀번호 제외 기본 정보만 필수
        const basicFieldsFilled =
            fields.username.value.trim() &&
            fields.birth.value.trim() &&
            fields.age.value.trim() &&
            fields.email.value.trim();

        const genderSelected =
            document.querySelector('input[name="gender"]:checked') !== null;

        // 비밀번호 변경 시도 여부
        const isPasswordChangeRequested =
            fields.currentPw.value ||
            fields.newPw.value ||
            fields.newPwCheck.value;

        const isNewPwMatch =
            fields.newPw.value === fields.newPwCheck.value;

        const isNewPwNotSame =
            fields.newPw.value !== fields.currentPw.value;

        const canSubmit =
            basicFieldsFilled &&
            genderSelected &&
            (
                !isPasswordChangeRequested ||
                (isPasswordVerified && isNewPwMatch && isNewPwNotSame)
            );

        btnSave.disabled = !canSubmit;
    };

    // // 현재 비밀번호 실시간 서버 확인
    // fields.currentPw.addEventListener('change', async () => {
    //     const loggedInUserId = sessionStorage.getItem("user_id");
    //     const passwordToVerify = fields.currentPw.value;

    //     if (passwordToVerify.length === 0) return;

    //     try {
    //         const response = await fetch(`/users/verify-password`, {
    //             method: 'POST',
    //             headers: { 'Content-Type': 'application/json' },
    //             body: JSON.stringify({
    //                 user_id: loggedInUserId,
    //                 current_password: passwordToVerify
    //             })
    //         });

    //         const result = await response.json();
    //         console.log("서버 응답 결과:", result);

    //         if (result.success === true || result.success === "true") {
    //             currentMsg.innerText = "비밀번호 확인 완료";
    //             currentMsg.className = "status-text success visible";
    //             isPasswordVerified = true; // 검증 성공 상태 저장
    //         } else {
    //             currentMsg.innerText = "현재 비밀번호와 일치하지 않습니다.";
    //             currentMsg.className = "status-text error visible";
    //             isPasswordVerified = false;
    //         }
    //         updateButtonState(); // 버튼 활성화 상태 다시 계산
    //     } catch (error) {
    //         console.error("비밀번호 검증 오류:", error);
    //     }
    // });

    // 현재 비밀번호 실시간 서버 확인
    fields.currentPw.addEventListener('input', async () => {

        const password = fields.currentPw.value;
        const userId = sessionStorage.getItem("user_id");

        if (!password) {
            isPasswordVerified = false;
            currentMsg.classList.remove('visible');
            updateButtonState();
            return;
        }

        const response = await fetch(`/users/verify-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userId,
                current_password: password
            })
        });

        const result = await response.json();

        if (result.success) {
            currentMsg.innerText = "비밀번호 확인 완료";
            currentMsg.className = "status-text success visible";
            isPasswordVerified = true;
        } else {
            currentMsg.innerText = "현재 비밀번호와 일치하지 않습니다.";
            currentMsg.className = "status-text error visible";
            isPasswordVerified = false;
        }

        updateButtonState();
    });

    // 새 비밀번호 유효성 검사
    fields.newPw.addEventListener('input', async () => {
        const newPw = fields.newPw.value;
        const userId = sessionStorage.getItem("user_id");

        if (!newPw) {
            newMsg.classList.remove('visible');
            updateButtonState();
            return;
        }

        const response = await fetch(`/users/check-new-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userId,
                new_password: newPw
            })
        });

        const result = await response.json();
        if (result.is_same === true || result.is_same === "true") {
            newMsg.innerText = "사용 중인 비밀번호입니다.";
            newMsg.className = "status-text error visible";
        } else {
            newMsg.innerText = "사용 가능한 비밀번호입니다.";
            newMsg.className = "status-text success visible";
        }

        validateMatch();
        updateButtonState();
    });

    // 새 비밀번호 확인 입력 시
    const validateMatch = () => {
        if (fields.newPw.value && fields.newPwCheck.value) {
            checkMsg.classList.add('visible');
            checkMsg.innerText =
                fields.newPw.value === fields.newPwCheck.value
                    ? "비밀번호가 일치합니다."
                    : "비밀번호가 일치하지 않습니다.";
            checkMsg.className =
                fields.newPw.value === fields.newPwCheck.value
                    ? "status-text success visible"
                    : "status-text error visible";
        } else {
            checkMsg.classList.remove('visible');
        }
        updateButtonState();
    };

    fields.newPwCheck.addEventListener('input', () => {
        validateMatch();
        updateButtonState();
    });
    
    // 이메일 유효성 검사 추가
    fields.email.addEventListener('input', () => {
        const email = fields.email.value.trim();
        if (!email) {
            emailMsg.classList.remove('visible');
            emailMsg.innerText = '';
            updateButtonState();
            return;
        }

        const valid = isValidEmail(email);
        emailMsg.innerText = valid
            ? '올바른 이메일 형식입니다.'
            : '이메일 형식이 올바르지 않습니다.';
        emailMsg.className = `status-text ${valid ? 'success' : 'error'} visible`;

        updateButtonState();
    });

    /* 3. 각 입력창에 이벤트 리스너 등록 (실시간 체크) */

    // 모든 일반 인풋/날짜/숫자 요소에 input 이벤트 추가
    Object.values(fields).forEach(field =>
        field.addEventListener('input', updateButtonState)
    );

    // 성별 라디오 버튼에 change 이벤트 추가
    document.getElementsByName('gender').forEach(radio => {
        radio.addEventListener('change', updateButtonState);
    });

    document
        .querySelectorAll('input[name="gender"]')
        .forEach(radio =>
            radio.addEventListener('change', updateButtonState)
        );

    /* 5. X 버튼 (Clear) 클릭 시에도 버튼 상태 갱신 */
    document.querySelectorAll('.btn-clear').forEach(btn => {
        btn.addEventListener('click', function () {
            const inputEl = this.previousElementSibling;
            if (inputEl) {
                inputEl.value = '';
                const msgEl = this.closest('.form-group').querySelector('.status-text');
                if (msgEl) msgEl.classList.remove('visible');
                updateButtonState();
            }
        });
    });


    // 수정된 유저 데이터 저장(POST)
    const saveUserData = async () => {
        const loggedInUserId = sessionStorage.getItem("user_id");

        const updatedData = {
            user_id: loggedInUserId, // 수정할 대상을 식별하기 위해 세션 ID 포함
            user_name: fields.username.value,
            current_password: fields.currentPw.value,
            new_password: fields.newPw.value,
            user_birth: fields.birth.value,
            user_age: parseInt(fields.age.value,10),
            user_gender: document.querySelector('input[name="gender"]:checked').value,
            user_email: fields.email.value
        };
        console.log("서버로 보내는 데이터:", updatedData); 
        
        // 실제 서버 전송 로직
        try {
            const response = await fetch(`/users/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updatedData)
            });

            if (response.ok) {
                editModal.classList.add('show'); // 성공 시 모달 띄우기
            } else {
                alert("수정에 실패했습니다. 입력값을 확인해주세요.");
            }
        } catch (error) {
            console.error("저장 중 오류 발생:", error);
        }
    };

    /* 모달 제어 로직 */
    // 1. 완료 버튼(submit) 클릭 시 팝업 띄우기
    editForm.addEventListener('submit', (e) => {
        e.preventDefault(); // 페이지 이동을 일단 막음
        //editModal.classList.add('show'); // 팝업 노출
        saveUserData();
    });

    // 2. 팝업 내 '확인' 클릭 시 마이페이지로 이동
    confirmEdit.addEventListener('click', () => {
        editModal.classList.remove('show');
        window.location.href = "/mypage"; // 실제 이동 경로
    });

    // 3. 팝업 내 '취소' 클릭 시 팝업 닫기
    closeEdit.addEventListener('click', () => {
        editModal.classList.remove('show');
    });

    // 페이지 로드 시 실행
    loadUserData();
    
});
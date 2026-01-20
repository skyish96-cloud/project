import os
import time
import joblib
import pandas as pd
from datetime import datetime, timezone, timedelta

from algorithm.news_NPTI import add_db, ArticlesNPTI, ES_INDEX, es, err_article, load_joblib
from database import SessionLocal
from logger import Logger
from elasticsearch import helpers

import re

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import VotingClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LogisticRegression
from lightgbm import LGBMClassifier
from sklearn.metrics import classification_report, accuracy_score
from algorithm.news_classify_tokenizer import tokenizer_fi

logger = Logger().get_logger(__name__)

# 데이터 로드
df = pd.read_csv(r"D:\PROJECT\Project_team3\LLM_test\LLM_results\TRAIN_DATA_v2.csv")
df = df.dropna(subset=["content","final_article_type","final_information_type","final_viewpoint_type"])

X = df["content"]
y_ct = df["final_article_type"]
y_fi = df["final_information_type"]
y_pn = df["final_viewpoint_type"]

# 데이터 분할
X_tr, X_te, y_ct_tr, y_ct_te, y_fi_tr, y_fi_te, y_pn_tr, y_pn_te = train_test_split(
    X, y_ct, y_fi, y_pn, test_size=0.2, random_state=42, stratify=y_ct
)


# TF-IDF vectorizer(분류별)
tfidf_ct = TfidfVectorizer(
    ngram_range=(1, 2),
    max_features=15000,
    min_df=3,
    max_df=0.9
)

tfidf_fi = TfidfVectorizer(
    tokenizer=tokenizer_fi,
    token_pattern=None,
    ngram_range=(1, 3),
    max_features=20000,
    min_df=3,
    max_df=0.9
)

tfidf_pn = TfidfVectorizer(
    ngram_range=(1, 3),
    max_features=15000,
    min_df=3,
    max_df=0.9
)

X_ct_tr = tfidf_ct.fit_transform(X_tr)
X_fi_tr = tfidf_fi.fit_transform(X_tr)
X_pn_tr = tfidf_pn.fit_transform(X_tr)

# 앙상블 모델 생성 함수
def build_model():
    return VotingClassifier(
        estimators=[
            ("nb", MultinomialNB(alpha=0.1)),
            ("lr", LogisticRegression(class_weight="balanced", max_iter=1000)),
            ("lgbm", LGBMClassifier(class_weight="balanced", random_state=42))
        ],
        voting="soft"
    )
model_ct = build_model()
model_fi = build_model()
model_pn = build_model()

# 모델 학습
logger.info("[article_type] 학습 시작")
t = time.time()
model_ct.fit(X_ct_tr, y_ct_tr)
logger.info(f"[article_type] 완료 ({time.time()-t:.2f}s)")

logger.info("[info_type] 학습 시작 (n-gram)")
t = time.time()
model_fi.fit(X_fi_tr, y_fi_tr)
logger.info(f"[info_type] 완료 ({time.time()-t:.2f}s)")

logger.info("[view_type] 학습 시작")
t = time.time()
model_pn.fit(X_pn_tr, y_pn_tr)
logger.info(f"[view_type] 완료 ({time.time()-t:.2f}s)")

# Accuracy 평가
def evaluate_model(name, model, vectorizer, X_test, y_test):
    """
    name        : 'CT', 'FI', 'PN'
    model       : 해당 타겟 모델
    vectorizer  : 해당 타겟 TF-IDF
    X_test      : 테스트 본문
    y_test      : 테스트 라벨
    """
    X_vec = vectorizer.transform(X_test)
    preds = model.predict(X_vec)

    acc = accuracy_score(y_test, preds)
    report = classification_report(y_test, preds)

    logger.info(f"[{name}] Accuracy: {acc:.4f}")
    logger.info(f"{report}")

    return acc

acc_CT = evaluate_model("CT", model_ct, tfidf_ct, X_te, y_ct_te)
acc_FI = evaluate_model("FI", model_fi, tfidf_fi, X_te, y_fi_te)
acc_PN = evaluate_model("PN", model_pn, tfidf_pn, X_te, y_pn_te)

# joblib 저장
base_dir = os.path.dirname(os.path.abspath(__file__))
save_dir = os.path.join(base_dir, "saved_models")
os.makedirs(save_dir, exist_ok=True)

# 모델
joblib.dump(model_ct, os.path.join(save_dir, "model_ct.joblib"))
joblib.dump(model_fi, os.path.join(save_dir, "model_fi.joblib"))
joblib.dump(model_pn, os.path.join(save_dir, "model_pn.joblib"))
# vectorizer
joblib.dump(tfidf_ct, os.path.join(save_dir, "tfidf_ct.joblib"))
joblib.dump(tfidf_fi, os.path.join(save_dir, "tfidf_fi.joblib"))
joblib.dump(tfidf_pn, os.path.join(save_dir, "tfidf_pn.joblib"))
logger.info("NPTI 라벨링 학습 모델 및 벡터라이즈 저장 완료")


# NPTI 라벨링 함수(배치)
def classify_npti():
    add_db()
    db = SessionLocal()

    models = load_joblib()
    model_ct, tfidf_ct = models["ct"]
    model_fi, tfidf_fi = models["fi"]
    model_pn, tfidf_pn = models["pn"]

    try:
        logger.info("===== NPTI 배치 분류 시작 =====")
        logger.info(
            f"[MODEL ACCURACY] "
            f"article_type: {acc_CT:.2%} | "
            f"info_type: {acc_FI:.2%} | "
            f"view_type: {acc_PN:.2%}"
        )

        existing_ids = set(row[0] for row in db.query(ArticlesNPTI.news_id).all())
        logger.info(f"현재 DB에 등록된 기사 수: {len(existing_ids)}건")

        rows = helpers.scan(
            es,
            index=ES_INDEX,
            query={"query": {"match_all": {}}, "_source": ["content"]}
        )

        count = 0
        for row in rows:
            news_id = row["_id"]
            if news_id in existing_ids:
                continue

            content = row["_source"].get("content", "")
            if not content:
                continue

            try:
                # 길이
                length_type = "L" if len(content) >= 1000 else "S"

                # 예측
                ct = model_ct.predict(tfidf_ct.transform([content]))[0].upper()
                fi = model_fi.predict(tfidf_fi.transform([content]))[0].upper()
                pn = model_pn.predict(tfidf_pn.transform([content]))[0].upper()

                npti_code = length_type + ct + fi + pn

                record = ArticlesNPTI(
                    news_id=news_id,
                    length_type=length_type,
                    article_type=ct,
                    info_type=fi,
                    view_type=pn,
                    NPTI_code=npti_code,
                    updated_at=datetime.now(timezone(timedelta(hours=9)))
                )

                db.merge(record)
                count += 1

                if count % 100 == 0:
                    db.commit()
                    logger.info(f"{count}건 처리 중-----------------------")

            except Exception as e:
                logger.error(f"[기사 NPTI 분류 실패] news_id={news_id} / {e}")
                err_article(news_id, e)
                continue

        db.commit()
        logger.info(f"최종 {count}건 기사 NPTI 분류 완료")
        logger.info(f"article_type:{acc_CT:.2%}, info_type:{acc_FI:.2%}, view_type:{acc_PN:.2%} =====")

    except Exception as e:
        logger.error(f"전체 분류 프로세스 오류: {e}")
        db.rollback()

    finally:
        db.close()


# =========== TEST용 ================================================================================
def test_article(text: str):
    length_type = "L" if len(text) >= 1200 else "S"

    # CT
    ct_vec = tfidf_ct.transform([text])
    ct_pred = model_ct.predict(ct_vec)[0]
    ct_conf = model_ct.predict_proba(ct_vec)[0].max()

    # FI
    fi_vec = tfidf_fi.transform([text])
    fi_pred = model_fi.predict(fi_vec)[0]
    fi_conf = model_fi.predict_proba(fi_vec)[0].max()

    # PN
    pn_vec = tfidf_pn.transform([text])
    pn_pred = model_pn.predict(pn_vec)[0]
    pn_conf = model_pn.predict_proba(pn_vec)[0].max()

    npti = length_type + ct_pred + fi_pred + pn_pred

    logger.info(f"NPTI CODE: {npti}")
    logger.info(f"CT: {ct_pred} ({ct_conf:.2%}), FI: {fi_pred} ({fi_conf:.2%}), PN: {pn_pred} ({pn_conf:.2%})")

    return {
        "npti_code": npti,
        "confidence_CT": ct_conf,
        "confidence_FI": fi_conf,
        "confidence_PN": pn_conf
    }


def test_article_csv(input_csv, output_csv):
    # CSV 파일 로딩
    df = pd.read_csv(input_csv)

    if 'content' not in df.columns:
        raise ValueError("CSV 파일에 'content'이라는 컬럼이 존재해야 합니다.")

    # NPTI 코드 생성
    df['npti_code'] = df['content'].apply(test_article)

    result = pd.json_normalize(df['npti_code'])
    df = pd.concat([df, result], axis=1)

    # 결과 저장
    df.to_csv(output_csv, index=False)
    logger.info("NPTI 분류 및 결과 저장 완료")

# 벌크 기사 NPTI 분류 테스트 ==================================================================================
if __name__ == "__main__":
    input_csv = r"NPTI_classify_test\sample_data_0107_v02.csv"
    output_csv = r"NPTI_classify_test\sample_data_0108_v01_result.csv"

    test_article_csv(input_csv, output_csv)


# 개별 기사 NPTI 분류 테스트 ==================================================================================
# if __name__ == "__main__":
#     sample_text = """
#
# 정의선 현대차그룹 회장이 세계 최대 IT·가전 전시회 ‘CES 2026’ 행사장에서 젠슨 황 엔비디아 최고경영자(CEO)와 다시 만났다. 지난해 이재용 삼성전자 회장과 함께한, 이른바 ‘깐부회동’ 이후 약 3개월 만이다.
#
# 정 회장은 6일(현지시간) 오후 1시 50분부터 30분가량 미국 라스베이거스 퐁텐블루 호텔에서 황 CEO와 비공개 회동을 했다.
#
# 정 회장은 황 CEO와의 회동 전 엔비디아 제품을 둘러보고 황 CEO의 딸인 메디슨과 담소를 나누는 등 ‘깐부’의 친분을 드러냈다.
#
# 업계에선 이 회동을 두고 현대자동차와 엔비디아가 향후 자율주행 분야에서 협업을 확대하는 것이 아니냐는 관측이 나온다.
#
# 황 CEO는 ‘CES 2026’ 기조연설에서 자율주행 차량 플랫폼 ‘알파마요’(Alpamayo)’와 ‘클래식AV’ 스택을 공개하며 메르세데스 벤츠와의 자율주행차 출시 계획을 알렸다.
#
# 그는 연설에서 “이번 협력이 메르세데스 벤츠에 국한되지 않고 자율주행 생태계 전반으로 확장될 것”이라고 밝히며 타 기업과의 협업 의지를 드러낸 바 있다.
#
# 이에 따라 현대차 주가도 들썩이고 있다. 황 CEO의 발언 뒤 두 기업 총수가 회동한다는 점에서 현대차가 엔비디아를 등에 업고 자율주행 사업 전면에 나설지 모른다는 기대감이 반영된 것으로 풀이된다. 현대차 주가는 오전 10시 기준 33만500원으로, 전일 대비 2만2500원, 7.31% 오른 수치를 기록 중이다.
#
# 한편, 현대차그룹은 지난해부터 엔비디아와 협업 체계를 확대해 왔다. 지난해 1월 엔비디아와 전략적 파트너십을 체결한 데 이어 10월에는 국내 피지컬 AI 역량 고도화를 위한 업무협약을 체결했다. 현대차그룹은 엔비디아가 피지컬 AI 비전을 현실화할 최적의 파트너라고 판단하고 엔비디아의 AI 인프라, 시뮬레이션 라이브러리, 프레임워크를 적극적으로 활용한다는 방침이다.
#
# """
#
#     test_article(sample_text)




# NPTI 분류 호출 ==================================================================================
# if __name__ == "__main__":
#     classify_npti()
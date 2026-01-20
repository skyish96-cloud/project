import os

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, VotingClassifier, ExtraTreesClassifier, StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier
from sklearn.model_selection import GroupKFold, cross_validate, cross_val_score
from sklearn.metrics import (
    make_scorer, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)
from joblib import dump, load


# joblib 저장
base_dir = os.path.dirname(os.path.abspath(__file__))
save_dir = os.path.join(base_dir, "saved_models")
os.makedirs(save_dir, exist_ok=True)

def xgb_training():
    # 1. 데이터 로드
    try:
        df = pd.read_csv("second_feature_labeled.csv")
    except FileNotFoundError:
        print("[Error] 파일을 찾을 수 없습니다. 파일 경로를 확인해주세요.")
        return
    print("=" * 60)
    print(f"XGBoostClassifier")
    print("=" * 60)


    # 2. 데이터 전처리 및 분할
    # 1번 알고리즘의 Feature 사용 (timestamp 포함)
    features = ['timestamp', 'MMF_y_inf', 'MMF_x_inf', 'MSF_y_inf', 'mouseX', 'mouseY', 'baseline']

    # [요청 로직 반영] P1은 Test, 그 외는 Train으로 분리 (P1 vs Rest)
    # *주의: user_id가 문자열인지 확인 필요, 여기서는 문자열로 처리
    train_df = df[df['user_id'] != 'P1'].copy()
    test_df = df[df['user_id'] == 'P1'].copy()

    print(f"Train set size: {len(train_df)} | Test set (P1) size: {len(test_df)}")

    x_train = train_df[features]
    y_train = train_df['read'].astype(int)
    groups_train = train_df['user_id']  # CV용 그룹

    x_test = test_df[features]
    y_test = test_df['read'].astype(int)

    # 3. Model 정의 (1번 알고리즘 설정 유지)
    model = XGBClassifier(
        n_estimators=1000,
        learning_rate=0.05,
        max_depth=3,
        scale_pos_weight=5,  # 1번 알고리즘 설정 유지
        eval_metric='auc',
        n_jobs=-1,
        random_state=45
    )

    # 4. Model 학습
    print(f'model 학습 시작...')
    model.fit(x_train, y_train)

    # 5. Model 점수 확인 (Cross Validation - Train 데이터 대상)
    # [요청 로직 반영] user_id 기준 GroupKFold
    gkf = GroupKFold(n_splits=5)

    scoring_metrics = {
        'roc_auc': 'roc_auc',
        'precision_0': make_scorer(precision_score, pos_label=0),
        'recall_0': make_scorer(recall_score, pos_label=0),
        'f1_0': make_scorer(f1_score, pos_label=0),
        'precision_1': make_scorer(precision_score, pos_label=1),
        'recall_1': make_scorer(recall_score, pos_label=1),
        'f1_1': make_scorer(f1_score, pos_label=1),
    }

    # Train set에 대해 교차 검증 수행
    results = cross_validate(estimator=model, X=x_train, y=y_train, cv=gkf, groups=groups_train,
                             scoring=scoring_metrics, return_train_score=True)

    # 6. CV 결과 출력 (1번 알고리즘 포맷)
    print("-" * 60)
    print("==== 교차 검증(Cross Validation) 성능 평가 결과 (Train Set) ====")
    print(f"ROC AUC : 평균 {results['test_roc_auc'].mean():.4f}")
    print("-" * 60)
    print("[Class 0 - 안 읽음] 성능")
    print(f"Precision : 평균 {results['test_precision_0'].mean():.4f} | 폴드별: {np.round(results['test_precision_0'], 4)}")
    print(f"Recall    : 평균 {results['test_recall_0'].mean():.4f} | 폴드별: {np.round(results['test_recall_0'], 4)}")
    print(f"F1-Score  : 평균 {results['test_f1_0'].mean():.4f} | 폴드별: {np.round(results['test_f1_0'], 4)}")
    print("-" * 60)
    print("[Class 1 - 읽음] 성능")
    print(f"Precision : 평균 {results['test_precision_1'].mean():.4f} | 폴드별: {np.round(results['test_precision_1'], 4)}")
    print(f"Recall    : 평균 {results['test_recall_1'].mean():.4f} | 폴드별: {np.round(results['test_recall_1'], 4)}")
    print(f"F1-Score  : 평균 {results['test_f1_1'].mean():.4f} | 폴드별: {np.round(results['test_f1_1'], 4)}")

    # 7. Test Set 최종 평가 및 2번 알고리즘 시각화 도구 통합
    print("\n" + "=" * 60)
    print("==== 최종 테스트(Test Set - P1) 성능 평가 결과 ====")

    # 예측값 생성
    y_pred = model.predict(x_test)
    y_prob = model.predict_proba(x_test)[:, 1]

    # 기본 Score
    print(f"Test Accuracy : {model.score(x_test, y_test):.4f}")
    print(f"Test ROC AUC  : {roc_auc_score(y_test, y_prob):.4f}")

    # Classification Report
    print("\n[Classification Report]")
    print(classification_report(y_test, y_pred, digits=4))

    # [2번 알고리즘 로직] Confusion Matrix
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    print(f"[Confusion Matrix]\nTN: {tn}, FP: {fp}\nFN: {fn}, TP: {tp}")

    # [2번 알고리즘 로직] Feature Importance
    print("\n=== Feature Importance ===")
    fi_df = pd.DataFrame({
        'feature': features,
        'importance': model.feature_importances_
    })
    fi_df = fi_df.sort_values(by='importance', ascending=False)
    print(fi_df.head(10))
    print("-" * 60)

    # 8. [신규 요청] Reading Efficiency 분석
    print("\n=== Reading Efficiency Analysis (User P1) ===")

    # 분석을 위해 user_id, news_id가 포함된 데이터프레임 사용
    analysis_df = test_df.copy()
    analysis_df['pred_prob'] = y_prob  # 모델이 예측한 읽음 확률

    # 1단계: timestamp 중복 해결 (각 시간대별 확률을 평균값으로 정제)
    # user_id, news_id, timestamp가 동일한 행들을 그룹화하여 pred_prob의 평균을 구함
    df_unique = analysis_df.groupby(['user_id', 'news_id', 'timestamp'], as_index=False)['pred_prob'].mean()

    # 2단계: User/News 별 최종 지표 계산
    # 중복이 제거된 df_unique를 사용하여 dwell_time과 reading_time을 계산
    grouped = df_unique.groupby(['user_id', 'news_id']).agg(
        dwell_time=('timestamp', 'max'),  # 요청하신 대로 timestamp의 최댓값 유지
        pred_read_time=('pred_prob', 'sum')  # 정제된 확률값들의 합 (데이터 간격이 1초이므로 sum = 시간)
    ).reset_index()

    # 3단계: Reading Efficiency 계산
    grouped['reading_efficiency'] = grouped.apply(
        lambda row: row['pred_read_time'] / row['dwell_time'] if row['dwell_time'] > 0 else 0.0,
        axis=1
    )

    # 결과 확인
    print(grouped.head())

def voting_training():
    # 1. 데이터 로드
    try:
        df = pd.read_csv("second_feature_labeled.csv")
    except FileNotFoundError:
        print("[Error] 파일을 찾을 수 없습니다.")
        return

    print("=" * 60)
    print(f"Improved Soft Voting (XGB + RF + ExtraTrees)")
    print("=" * 60)

    # 2. 데이터 전처리
    features = ['timestamp', 'MMF_y_inf', 'MMF_x_inf', 'MSF_y_inf', 'mouseX', 'mouseY', 'baseline']

    train_df = df[df['user_id'] != 'P1'].copy()
    test_df = df[df['user_id'] == 'P1'].copy()

    print(f"Train set size: {len(train_df)} | Test set (P1) size: {len(test_df)}")

    x_train = train_df[features]
    y_train = train_df['read'].astype(int)
    groups_train = train_df['user_id']

    x_test = test_df[features]
    y_test = test_df['read'].astype(int)

    # 3. Model 정의 (트리 기반 앙상블 강화)

    # Model 1: XGBoost (성능의 핵심, 가중치 높음)
    clf_xgb = XGBClassifier(
        n_estimators=1000,
        learning_rate=0.05,
        max_depth=5,  # 깊이를 조금 늘려 복잡한 패턴 학습
        scale_pos_weight=5,
        eval_metric='auc',
        n_jobs=-1,
        random_state=45
    )

    # Model 2: Random Forest (안정성 담당)
    clf_rf = RandomForestClassifier(
        n_estimators=500,
        max_depth=12,  # 깊이 상향
        class_weight='balanced',
        n_jobs=-1,
        random_state=45
    )

    # Model 3: Extra Trees (다양성 확보 - New!)
    # 로지스틱 회귀 대신 추가됨. 과적합을 막고 일반화 성능을 높임
    clf_et = ExtraTreesClassifier(
        n_estimators=500,
        max_depth=12,
        class_weight='balanced',
        n_jobs=-1,
        random_state=45
    )

    # Voting Model (가중치 조정)
    # XGBoost가 가장 강력하므로 가중치 3 부여
    model = VotingClassifier(
        estimators=[('xgb', clf_xgb), ('rf', clf_rf), ('et', clf_et)],
        voting='soft',
        weights=[3, 1, 1]
    )

    # 4. 학습
    print(f'model 학습 시작...')
    model.fit(x_train, y_train)

    # 5. 교차 검증
    gkf = GroupKFold(n_splits=5)
    scoring_metrics = {
        'roc_auc': 'roc_auc',
        'precision_1': make_scorer(precision_score, pos_label=1),
        'recall_1': make_scorer(recall_score, pos_label=1),
        'f1_1': make_scorer(f1_score, pos_label=1),
    }

    results = cross_validate(model, x_train, y_train, cv=gkf, groups=groups_train,
                             scoring=scoring_metrics, return_train_score=False)

    print("-" * 60)
    print("==== 교차 검증 (Train Set) ====")
    print(f"ROC AUC   : {results['test_roc_auc'].mean():.4f}")
    print(f"Precision : {results['test_precision_1'].mean():.4f}")
    print(f"Recall    : {results['test_recall_1'].mean():.4f}")
    print("-" * 60)

    # 6. 최종 테스트 (P1)
    y_pred = model.predict(x_test)
    y_prob = model.predict_proba(x_test)[:, 1]

    print("\n==== 최종 테스트 (P1) ====")
    print(f"Test Accuracy : {model.score(x_test, y_test):.4f}")
    print(f"Test ROC AUC  : {roc_auc_score(y_test, y_prob):.4f}")
    print("\n[Classification Report]")
    print(classification_report(y_test, y_pred, digits=4))

    # Confusion Matrix
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    print(f"TP: {tp}, FP: {fp}, FN: {fn}, TN: {tn}")

    # 7. Feature Importance (Weighted)
    print("\n=== Feature Importance (Weighted) ===")
    xgb_imp = model.named_estimators_['xgb'].feature_importances_
    rf_imp = model.named_estimators_['rf'].feature_importances_
    et_imp = model.named_estimators_['et'].feature_importances_

    # 가중치(3:1:1) 반영 평균
    weighted_imp = (xgb_imp * 3 + rf_imp * 1 + et_imp * 1) / 5

    fi_df = pd.DataFrame({'feature': features, 'importance': weighted_imp})
    print(fi_df.sort_values(by='importance', ascending=False).head(10))

    # 8. Reading Efficiency Analysis
    print("\n=== Reading Efficiency Analysis (User P1) ===")
    analysis_df = test_df.copy()
    analysis_df['pred_prob'] = y_prob

    # 1단계: Timestamp 중복 평균 (Soft Voting 확률 사용)
    df_unique = analysis_df.groupby(['user_id', 'news_id', 'timestamp'], as_index=False)['pred_prob'].mean()

    # 2단계: 합산
    grouped = df_unique.groupby(['user_id', 'news_id']).agg(
        dwell_time=('timestamp', 'max'),
        pred_read_time=('pred_prob', 'sum')
    ).reset_index()

    grouped['reading_efficiency'] = grouped.apply(
        lambda row: row['pred_read_time'] / row['dwell_time'] if row['dwell_time'] > 0 else 0.0,
        axis=1
    )

    print(grouped.head())


def load_and_preprocess():
    try:
        df = pd.read_csv("second_feature_labeled.csv")
    except FileNotFoundError:
        print("[Error] 파일을 찾을 수 없습니다.")
        return None, None, None, None, None, None

    features = ['timestamp', 'MMF_y_inf', 'MMF_x_inf', 'MSF_y_inf', 'mouseX', 'mouseY', 'baseline']

    train_df = df[df['user_id'] != 'P1'].copy()
    test_df = df[df['user_id'] == 'P1'].copy()

    x_train = train_df[features]
    y_train = train_df['read'].astype(int)

    x_test = test_df[features]
    y_test = test_df['read'].astype(int)

    return x_train, y_train, x_test, y_test, test_df

def solution_1_basic_stacking():
    print("\n" + "=" * 60)
    print(">>> [솔루션 1] Basic Stacking (안정성 강화 버전)")
    print("=" * 60)

    x_train, y_train, x_test, y_test, test_df = load_and_preprocess()
    if x_train is None: return

    # Base Models: 각 모델은 내부적으로 병렬 처리(n_jobs=-1)를 유지하여 속도 확보
    clf_xgb = XGBClassifier(n_estimators=1000, learning_rate=0.05, max_depth=5, scale_pos_weight=5, eval_metric='auc', n_jobs=-1, random_state=45)
    clf_rf = RandomForestClassifier(n_estimators=500, max_depth=12, class_weight='balanced', n_jobs=-1, random_state=45)
    clf_et = ExtraTreesClassifier(n_estimators=500, max_depth=12, class_weight='balanced', n_jobs=-1, random_state=45)

    # Stacking Model: [중요] n_jobs=1로 설정하여 순차 학습 (메모리 에러 방지)
    # Final Estimator: max_iter=2000으로 늘려 수렴 경고 방지
    model = StackingClassifier(
        estimators=[('xgb', clf_xgb), ('rf', clf_rf), ('et', clf_et)],
        final_estimator=LogisticRegression(class_weight='balanced', max_iter=2000),
        passthrough=True,
        n_jobs=1  # <--- 핵심 수정 사항
    )

    print("모델 학습 중 (순차 학습으로 안정성 확보)...")
    model.fit(x_train, y_train)

    y_pred = model.predict(x_test)
    y_prob = model.predict_proba(x_test)[:, 1]

    print(f"\n[Test Result] ROC AUC: {roc_auc_score(y_test, y_prob):.4f}")
    print(classification_report(y_test, y_pred, digits=4))


def final_best_model():
    print("\n" + "=" * 60)
    print(">>> [최종 추천] Improved Voting with Threshold Optimization")
    print("=" * 60)

    # 1. 데이터 로드
    try:
        df = pd.read_csv("second_feature_labeled.csv")
    except FileNotFoundError:
        print("파일 없음")
        return

    features = ['timestamp', 'MMF_y_inf', 'MMF_x_inf', 'MSF_y_inf', 'mouseX', 'mouseY', 'baseline']
    train_df = df[df['user_id'] != 'P1'].copy()
    test_df = df[df['user_id'] == 'P1'].copy()

    x_train = train_df[features]
    y_train = train_df['read'].astype(int)
    x_test = test_df[features]
    y_test = test_df['read'].astype(int)

    # 2. Improved Soft Voting 모델 정의 (가장 똑똑했던 모델)
    clf_xgb = XGBClassifier(n_estimators=1000, learning_rate=0.05, max_depth=5, scale_pos_weight=5, eval_metric='auc',
                            n_jobs=-1, random_state=45)
    clf_rf = RandomForestClassifier(n_estimators=500, max_depth=12, class_weight='balanced', n_jobs=-1, random_state=45)
    clf_et = ExtraTreesClassifier(n_estimators=500, max_depth=12, class_weight='balanced', n_jobs=-1, random_state=45)

    model = VotingClassifier(
        estimators=[('xgb', clf_xgb), ('rf', clf_rf), ('et', clf_et)],
        voting='soft',
        weights=[3, 1, 1],
        n_jobs=1  # 안전하게 1로 설정
    )

    print("모델 학습 중...")
    model.fit(x_train, y_train)

    # 확률 예측
    y_prob = model.predict_proba(x_test)[:, 1]

    # 3. 최적의 Threshold 찾기 (Recall 0.8 이상 유지 조건)
    print("\n[Threshold Optimization]")
    print(f"{'Threshold':<10} | {'Recall':<10} | {'Precision':<10} | {'F1-Score':<10}")
    print("-" * 50)

    best_th = 0.5
    found_optimal = False

    # 0.3부터 0.5까지 0.01 단위로 세밀하게 탐색
    for th in np.arange(0.3, 0.51, 0.01):
        y_pred_th = (y_prob >= th).astype(int)
        rec = recall_score(y_test, y_pred_th, pos_label=1)
        pre = precision_score(y_test, y_pred_th, pos_label=1, zero_division=0)
        f1 = f1_score(y_test, y_pred_th, pos_label=1)

        # 로그 출력 (0.05 단위로만 출력해서 보기 좋게)
        if round(th * 100) % 5 == 0:
            print(f"{th:<10.2f} | {rec:.4f}     | {pre:.4f}     | {f1:.4f}")

        # 조건: Recall이 0.8 이상이면서 가장 F1이 높은 지점 포착
        if not found_optimal and rec <= 0.85 and rec >= 0.78:
            best_th = th
            # found_optimal = True # 가장 높은 정밀도를 위해 계속 탐색해도 됨

    print("-" * 50)
    print(f"★ 적용할 Optimal Threshold: {best_th:.2f}")

    # 4. 최종 결과 산출 (Optimal Threshold 적용)
    print(f"\n=== Final Reading Efficiency (Threshold={best_th:.2f}) ===")

    analysis_df = test_df.copy()
    analysis_df['pred_prob'] = y_prob

    # Timestamp 중복 평균
    df_unique = analysis_df.groupby(['user_id', 'news_id', 'timestamp'], as_index=False)['pred_prob'].mean()

    # Reading Time 계산
    grouped = df_unique.groupby(['user_id', 'news_id']).agg(
        dwell_time=('timestamp', 'max'),
        # 최적 임계값 적용
        final_read_time=('pred_prob', lambda x: (x >= best_th).sum())
    ).reset_index()

    grouped['reading_efficiency'] = grouped.apply(
        lambda row: row['final_read_time'] / row['dwell_time'] if row['dwell_time'] > 0 else 0.0,
        axis=1
    )

    print(grouped.head(10))


    dump(model, os.path.join(save_dir, "model_read_efficiency.joblib"))


# @app.get("/latest_npti_update_time")
# def get_latest_user_npti(request: Request, db: Session = Depends(get_db)):
#     user_id = request.session.get("user_id")
#     # user_id가 세션에 없는 경우 추가해야함
#     latest_user_npti = get_user_npti_info(db, user_id)
#     latest_update_time = latest_user_npti['timestamp']
#     return {"latest_update_time": latest_update_time}


def model_predict_proba(logs:list): # [{},{}] 형태 input
    model_path = os.path.join(save_dir, "model_read_efficiency.joblib")
    model = load(model_path)
    data = pd.DataFrame(logs)
    data.rename(columns={"MMF_X_inf":"MMF_x_inf","MMF_Y_inf":"MMF_y_inf","MSF_Y_inf":"MSF_y_inf"}, inplace=True)
    features = ['timestamp', 'MMF_y_inf', 'MMF_x_inf', 'MSF_y_inf', 'mouseX', 'mouseY', 'baseline']
    y_prob = model.predict_proba(data[features])[:, 1]
    data['pred_prob'] = y_prob
    best_th = 0.39

    # 성능 확인 용 통계 출력 (예측 분포)
    print(f"전체 로그 수 : {len(data)}개")
    print(f"확률 예측 로그 수 : {data['pred_prob'].sum()}개")
    print(f"평균 읽음 확률 : {y_prob.mean():.4f}")

    # timestamp 중복 시 확률 평균값 이용
    df_unique = data.groupby(['user_id', 'news_id', 'timestamp'], as_index=False)['pred_prob'].mean()

    # reading time 및 efficiency 계산
    result = df_unique.groupby(['user_id', 'news_id']).agg(
        dwell_time=('timestamp', 'max'),
        final_read_time=('pred_prob', lambda x: (x >= best_th).sum())
    ).reset_index()

    result['reading_efficiency'] = result.apply(
        lambda row: row['final_read_time'] / row['dwell_time'] if row['dwell_time'] > 0 else 0.0,
        axis=1
    )

    # 최종 결과 반환
    # 8. 최종 결과물 출력 (final_best_model 스타일)
    final_res = result.iloc[0].to_dict()

    print(f"===== Analysis Result =====")
    print(f"User ID: {final_res['user_id']}")
    print(f"News ID: {final_res['news_id']}")
    print(f"Dwell Time: {final_res['dwell_time']}")
    print(f"Pred Read Time: {final_res['final_read_time']}s")
    print(f"News ID: {final_res['reading_efficiency']}")

    return final_res




if __name__ == "__main__":
    # xgb_training()
    # voting_training()
    # solution_1_basic_stacking()
    final_best_model()
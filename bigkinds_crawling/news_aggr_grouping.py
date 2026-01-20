from kiwipiepy import Kiwi
from matplotlib import pyplot as plt
from sklearn.metrics.pairwise import cosine_similarity as cosine
import math
import numpy as np
from elasticsearch_index.es_aggr import tokens_aggr
from elasticsearch_index.es_raw import es
from datetime import datetime
from logger import Logger
from sklearn.feature_extraction.text import TfidfVectorizer
from elasticsearch import helpers

logger = Logger().get_logger(__name__)

def related_news(news_title:str, exclude_id:str, category:str):
    body = {
        "size":5,
        "_source":["news_id","title","pubdate","media","img"],
        "query":{
            "bool":{
                "must":[
                    {"multi_match":{
                        "query":news_title,
                        "fields":["title", "content"]
                    }}
                ],
                "must_not":[
                    {"term":{"news_id":exclude_id}},
                ],
                "filter":[
                    {"term":{"category":category}},
                ]
            }
        }
    }
    try:
        res = es.search(index="news_raw", body=body)
        hits = res["hits"]["hits"]
        results = []
        for hit in hits:
            doc = hit["_source"]
            doc["_score"] = hit["_score"]
            results.append(doc)
        return results
    except Exception as e:
        logger.info(f"검색 중 에러 발생 : {e}")
        return None


kiwi = Kiwi()
def news_aggr(*args):
    processed_ids = set()
    try:
        # 1. 처리된 기사 ID 확인
        query = {
            "_source": ["news_id"],
            "size": 10000,
            "query": {"range": {"timestamp": {"gte": "now-1h", "lte": "now"}}}
        }
        es.indices.refresh(index="news_aggr")
        res = es.search(index="news_aggr", body=query)
        for hit in res["hits"]["hits"]:
            processed_ids.add(hit["_source"].get("news_id"))

        # 2. Raw 기사 가져오기
        raw_query = {
            "_source": ["news_id", "title", "content", "tag"],
            "size": 10000,
            "query": {"range": {"timestamp": {"gte": "now-1h", "lte": "now"}}}
        }
        raw_res = es.search(index="news_raw", body=raw_query)

        # 리스트 초기화
        breaking_list = []
        norm_list = []
        target_breaking_ids_list = []
        remove_breaking_list = []  # [New] 그룹핑에서 제외할 기사 ID 목록

        # ------------------------------------------------------------------
        # [A] 새로운 기사 분류 및 토큰화
        # ------------------------------------------------------------------
        for hit in raw_res["hits"]["hits"]:
            source = hit["_source"]
            news_id = source.get("news_id")

            if news_id not in processed_ids:
                tag = str(source.get("tag", ""))
                title_token = str(source.get("title", ""))
                content_token = str(source.get("content", ""))
                weighted_token = (title_token + " ") * 3 + content_token

                # 형태소 분석 (숫자 포함 필수)
                token_result = tokens_aggr(weighted_token, kiwi)

                item_data = {"news_id": news_id, "token": token_result, "tag": tag}

                if tag == "속보":
                    # [조건] 제목이 본문에 포함된 경우 (부실/중복 속보)
                    if title_token in content_token:
                        # 1. 분석/저장 대상에는 포함 (breaking_list)
                        breaking_list.append(item_data)
                        target_breaking_ids_list.append(news_id)
                        # 2. 삭제 대상 목록에 등록 (나중에 그룹핑에서 뺄 것임)
                        remove_breaking_list.append(news_id)
                        logger.info(f"그룹핑 제외 대상 등록: {news_id}")

                    # [조건] 정상 속보
                    else:
                        breaking_list.append(item_data)
                        target_breaking_ids_list.append(news_id)

                elif tag == "일반":
                    norm_list.append(item_data)

        logger.info(f"새로 수집: 속보 {len(breaking_list)}건 (제외대상 {len(remove_breaking_list)}건 포함), 일반 {len(norm_list)}건")

        # ------------------------------------------------------------------
        # [B] 분석 대상(Target) 선정 로직 (Fallback 구현)
        # ------------------------------------------------------------------
        target_breaking_list = []
        is_fallback_mode = False

        if breaking_list:
            target_breaking_list = breaking_list
            logger.info(">>> [모드] 신규 속보 데이터 분석")

        else:
            logger.info(">>> [모드] 신규 속보 없음 -> 기존 news_aggr 데이터 조회 (Fallback)")
            is_fallback_mode = True

            fallback_query = {
                "size": 10000,
                "_source": ["news_id", "tokens", "tag"],
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"timestamp": {"gte": "now-1h", "lte": "now"}}},
                            {"term": {"tag": "속보"}}
                        ]
                    }
                }
            }
            fallback_res = es.search(index="news_aggr", body=fallback_query)
            target_breaking_ids_list = []

            for hit in fallback_res["hits"]["hits"]:
                src = hit["_source"]
                tokens_data = src.get("tokens", [])
                extracted_terms = [t.get("term", "") for t in tokens_data]
                reconstructed_token_str = " ".join(extracted_terms)

                if reconstructed_token_str.strip():
                    target_breaking_list.append({
                        "news_id": src.get("news_id"),
                        "token": reconstructed_token_str,
                        "tag": "속보"
                    })
                    target_breaking_ids_list.append(src.get("news_id"))

        # ------------------------------------------------------------------
        # [C] 속보 TF-IDF 계산 (전체 리스트 대상)
        # ------------------------------------------------------------------
        breaking_tfidf = None
        breaking_actions = []

        if target_breaking_list:
            breaking_corpus = [item['token'] for item in target_breaking_list]

            # TF-IDF 수행 (여기서는 제외 대상도 포함해서 계산됨)
            breaking_vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=3000)
            breaking_tfidf = breaking_vectorizer.fit_transform(breaking_corpus)
            breaking_features = breaking_vectorizer.get_feature_names_out()

            # [저장 로직] 제외 대상도 Index에는 저장 (Requirement 충족)
            if not is_fallback_mode:
                for i, item in enumerate(target_breaking_list):
                    row = breaking_tfidf.getrow(i).toarray().flatten()
                    tokens_score_list = [
                        {"term": str(breaking_features[idx]), "score": float(row[idx])}
                        for idx in range(len(row)) if row[idx] > 0
                    ]
                    tokens_score_list = sorted(tokens_score_list, key=lambda x: x['score'], reverse=True)

                    action = {
                        "_index": "news_aggr", "_id": item['news_id'],
                        "_source": {
                            "news_id": item['news_id'], "tokens": tokens_score_list,
                            "tag": item['tag'], "timestamp": datetime.now().astimezone().isoformat(timespec="seconds")
                        }
                    }
                    breaking_actions.append(action)
                logger.info(f"신규 속보 저장 대기: {len(breaking_actions)}건")

        # ------------------------------------------------------------------
        # [D] 일반 기사 TF-IDF 및 저장
        # ------------------------------------------------------------------
        norm_actions = []
        if norm_list:
            norm_corpus = [item['token'] for item in norm_list]
            norm_vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=3000)
            norm_tfidf = norm_vectorizer.fit_transform(norm_corpus)
            norm_features = norm_vectorizer.get_feature_names_out()

            for i, item in enumerate(norm_list):
                row = norm_tfidf.getrow(i).toarray().flatten()
                tokens_score_list = [
                    {"term": str(norm_features[idx]), "score": float(row[idx])}
                    for idx in range(len(row)) if row[idx] > 0
                ]
                tokens_score_list = sorted(tokens_score_list, key=lambda x: x['score'], reverse=True)
                action = {
                    "_index": "news_aggr", "_id": item['news_id'],
                    "_source": {
                        "news_id": item['news_id'], "tokens": tokens_score_list,
                        "tag": item['tag'], "timestamp": datetime.now().astimezone().isoformat(timespec="seconds")
                    }
                }
                norm_actions.append(action)

        # ------------------------------------------------------------------
        # [E] ES Bulk 저장
        # ------------------------------------------------------------------
        actions = breaking_actions + norm_actions
        if actions:
            success, _ = helpers.bulk(es, actions)
            logger.info(f"ES Bulk Insert Success: {success}건")

        if not actions and not target_breaking_list:
            return {"status": "no data to process"}

        # ------------------------------------------------------------------
        # [F] 그룹핑 및 시각화 (속보 대상) - 제외 대상 필터링 적용!
        # ------------------------------------------------------------------
        final_groups = []
        groups_1st = []

        # [1] 필터링 준비: remove_breaking_list에 없는 기사들만 골라내기
        grouping_target_list = []
        valid_indices = []
        remove_set = set(remove_breaking_list)

        # target_breaking_list는 전체 데이터이므로 인덱스(i)가 TF-IDF 행렬의 행 번호와 일치함
        for i, item in enumerate(target_breaking_list):
            if item['news_id'] not in remove_set:
                grouping_target_list.append(item)
                valid_indices.append(i)  # 유효한 기사의 행 번호 저장

        logger.info(f"그룹핑 필터링: 전체 {len(target_breaking_list)}건 -> 그룹핑 대상 {len(grouping_target_list)}건")

        # [2] 그룹핑 실행 (필터링된 리스트 사용)
        if grouping_target_list and breaking_tfidf is not None:
            logger.info("--- 속보 기사 그룹핑 시작 ---")

            # [핵심] TF-IDF 행렬 Slicing: 유효한 행(valid_indices)만 뽑아서 새 행렬 생성
            filtered_tfidf_matrix = breaking_tfidf[valid_indices]

            # 코사인 유사도 계산 (필터링된 행렬 사용)
            sim_actions = cal_cosine_similarity(filtered_tfidf_matrix, grouping_target_list)

            # 1차 그룹핑 (Threshold 0.15)
            # 이유: 짧은 기사는 단어 하나만 달라도 유사도가 낮으므로 진입장벽을 낮춤
            groups_1st, edges = topic_grouping(sim_actions)
            logger.info(f"1차 그룹핑 완료: {len(groups_1st)}개 그룹")

            # 2차 병합 (Threshold 0.35)
            # 이유: 뭉쳐진 텍스트는 유사도가 높게 나오므로 엄격하게 검사
            all_news_dict = {item['news_id']: item for item in grouping_target_list}
            threshold = 0.35
            final_groups = merge_similar_groups(groups_1st, all_news_dict, threshold=threshold)
            logger.info(f"2차 병합 완료: {len(final_groups)}개 그룹")

            # 만약 그룹핑 결과가 없으면 개별 ID 리스트로 반환 (단, 필터링된 ID들만)
            if len(final_groups) < 1:
                filtered_ids = [item['news_id'] for item in grouping_target_list]
                final_groups = [[nid] for nid in filtered_ids]

            # # 시각화
            # time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            # graph_title = f"final_groups_threshold({threshold})_{time_str}"
            #
            # try:
            #     visualize_groups(final_groups, edges, title=graph_title)
            # except Exception as viz_err:
            #     logger.error(f"시각화 중 에러 발생: {viz_err}")

        # 결과 출력 및 반환
        print(f"is_fallback_mode : {is_fallback_mode}\n"
              f"target_breaking_ids_list(전체) : {target_breaking_ids_list}\n"
              f"removed_count : {len(remove_breaking_list)}\n"
              f"first_group : \n{groups_1st}\n"
              f"final_groups(필터링됨) : \n{final_groups}")

        res = {
            "target_breaking_ids_list": target_breaking_ids_list,
            "first_group": groups_1st,
            "final_group": final_groups
        }

        q = args[-1]
        q.put(res)
        return res

    except Exception as e:
        logger.error(f"news_aggr error: {e}")
        return {"status": "error", "message": str(e)}



def cal_cosine_similarity(tfidf_matrix, news_items):
    sim_matrix = cosine(tfidf_matrix)

    similarity_actions=[]
    for i in range(len(news_items)):
        # 자기 자신을 제외하고 유사도가 높은 순으로 정렬 (예: 상위 5개)
        # sim_matrix[i]는 i번째 기사와 다른 모든 기사 간의 점수
        sorted_indices = sim_matrix[i].argsort()[::-1]

        related_news = []
        for idx in sorted_indices:
            if i == idx: continue  # 자기 자신 제외
            score = float(sim_matrix[i][idx])
            if score < 0.2 : break  # 유사도 임계값 설정

            related_news.append({
                "news_id": news_items[idx]['news_id'],
                "score": score
            })
            # if len(related_news) >= 5: break  # 상위 5개만 저장

        if related_news:
            similarity_actions.append({
                    "news_id": news_items[i]['news_id'],
                    "related_news": related_news,
                    "timestamp": datetime.now().isoformat()
            })
    return similarity_actions


# 1. 1차 그룹핑 (기사 간 유사도 기반)
# ---------------------------------------------------------
def topic_grouping(news_group):
    """
    1차: 기사 간 유사도(Cosine Similarity) 결과를 바탕으로 그래프를 생성하고
    연결된 컴포넌트(Connected Components)를 찾아 그룹핑합니다.
    Returns: (groups, edges)
    """
    adj_list = {}
    all_nodes = set()
    edges = []

    for item in news_group:
        source_id = item['news_id']
        all_nodes.add(source_id)

        if source_id not in adj_list:
            adj_list[source_id] = set()

        for rel in item['related_news']:
            # score 0.15 이상만 유효한 엣지로 간주
            if rel['score'] >= 0.15:
                target_id = rel['news_id']
                all_nodes.add(target_id)

                # 양방향 연결
                adj_list[source_id].add(target_id)
                if target_id not in adj_list:
                    adj_list[target_id] = set()
                adj_list[target_id].add(source_id)

                # 시각화용 엣지 저장
                edge = tuple(sorted([source_id, target_id]))
                if edge not in [e[:2] for e in edges]:
                    edges.append((edge[0], edge[1], rel['score']))

    # BFS로 그룹 찾기
    visited = set()
    groups = []

    for node in all_nodes:
        if node not in visited:
            component = []
            queue = [node]
            visited.add(node)
            while queue:
                curr = queue.pop(0)
                component.append(curr)
                if curr in adj_list:
                    for neighbor in adj_list[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
            groups.append(component)

    return groups, edges


# ---------------------------------------------------------
# 2. 2차 그룹핑 (그룹 간 유사도 기반 병합)
# ---------------------------------------------------------
def merge_similar_groups(groups, all_news_dict, threshold:float = 0.25):
    """
    2차: 1차로 분류된 그룹들의 전체 텍스트를 합쳐서 다시 TF-IDF를 돌리고,
    그룹 간 유사도가 threshold 이상이면 병합합니다.
    """
    if len(groups) < 2:
        return groups

    # 1. 각 그룹의 텍스트 뭉치기
    group_texts = []
    for group in groups:
        combined_text = []
        for news_id in group:
            if news_id in all_news_dict:
                # tokens_aggr로 이미 토큰화된 문자열을 가져옴
                token_str = all_news_dict[news_id].get('token', '')
                combined_text.append(str(token_str))
        group_texts.append(" ".join(combined_text))

    # 2. 그룹 간 유사도 계산
    try:
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(group_texts)
        sim_matrix = cosine(tfidf_matrix)  # sklearn cosine_similarity
    except ValueError:
        # 텍스트가 비어있거나 하는 경우 원본 유지
        return groups

    # 3. 그룹 간 병합 그래프 생성
    n_groups = len(groups)
    adj = {i: set() for i in range(n_groups)}

    for i in range(n_groups):
        for j in range(i + 1, n_groups):
            if sim_matrix[i][j] >= threshold:
                adj[i].add(j)
                adj[j].add(i)

    # 4. BFS로 병합된 그룹 찾기
    visited = set()
    merged_groups = []

    for i in range(n_groups):
        if i not in visited:
            stack = [i]
            visited.add(i)
            new_big_group = []
            while stack:
                curr_idx = stack.pop()
                new_big_group.extend(groups[curr_idx])
                for neighbor in adj[curr_idx]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)
            merged_groups.append(new_big_group)

    return merged_groups


# ---------------------------------------------------------
# 3. 통합 시각화 함수
# ---------------------------------------------------------
def visualize_groups(groups, edges, title:str="News Grouping"):
    """
    그룹 결과를 시각화합니다. 서버 실행 시 plt.show()는 주의해야 합니다.
    """
    group_centers = []
    node_positions = {}

    if len(groups) > 0:
        colors = plt.cm.rainbow(np.linspace(0, 1, len(groups)))
        grid_cols = math.ceil(math.sqrt(len(groups)))
    else:
        colors = []
        grid_cols = 1

    grid_spacing = 4.0

    for i, group in enumerate(groups):
        cx = (i % grid_cols) * grid_spacing
        cy = (i // grid_cols) * grid_spacing
        group_centers.append((cx, cy))

        n_nodes = len(group)
        radius = 1.0 if n_nodes > 1 else 0

        for j, node_id in enumerate(group):
            angle = 2 * math.pi * j / n_nodes if n_nodes > 0 else 0
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            node_positions[node_id] = (x, y)

            plt.scatter(x, y, color=colors[i], zorder=5, edgecolors='black')
            plt.text(x, y + 0.15, node_id[:6], fontsize=7, ha='center', fontweight='bold')

    # 기존 기사 간 연결선 (Edges from 1st grouping)
    for u, v, score in edges:
        if u in node_positions and v in node_positions:
            x1, y1 = node_positions[u]
            x2, y2 = node_positions[v]
            plt.plot([x1, x2], [y1, y2], color='gray', alpha=0.5, linewidth=1, zorder=1)

    # 그룹 배경 원
    for i, (cx, cy) in enumerate(group_centers):
        group_radius = 1.8
        circle = plt.Circle((cx, cy), group_radius, color=colors[i], alpha=0.1, zorder=0)
        plt.gca().add_patch(circle)
        plt.text(cx, cy - group_radius - 0.2, f"Group {i + 1}", ha='center',
                 fontsize=12, fontweight='bold', color=colors[i])

    plt.title(title, fontsize=15)
    plt.axis('equal')
    plt.axis('off')
    plt.tight_layout()

    # [서버 환경 설정]
    # 실제 서버 배포 시에는 plt.show() 대신 plt.savefig('result.png') 등을 사용하세요.
    plt.savefig(f"{title}.png")
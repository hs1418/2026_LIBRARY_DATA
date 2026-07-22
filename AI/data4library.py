import os
import re
import requests
import html

# 도서관 정보나루 API 키 (환경변수)
DATA4LIBRARY_KEY = os.getenv("DATA4LIBRARY_KEY")

# 시드 데이터 파일 경로 (프로젝트 폴더 구조에 맞춰 필요시 조정)
SEEDS_FILE_PATH = os.path.join(os.path.dirname(__file__), "data", "fairytale_seeds.txt")


def load_fallback_books_from_seeds() -> dict:
    """
    data/fairytale_seeds.txt 파일에서 이야기별(RECOMMEND_1 ~ RECOMMEND_10) 
    사전 큐레이션 5권 도서 목록을 파싱하여 딕셔너리로 반환합니다.
    """
    fallback_map = {}
    
    # 파일이 존재하지 않는 경우를 대비한 최소 기본값 (1번 콩쥐팥쥐)
    default_books = [
        {"title": "콩쥐팥쥐", "author": "이성실 글 ; 박완서 그림", "publisher": "보림", "call_no": "813.8-보64ㅋ-2"},
        {"title": "화요일의 두꺼비", "author": "러셀 에릭슨 지음 ; 햇살과나무꾼 옮김", "publisher": "사계절", "call_no": "843-에296ㅎ"},
        {"title": "개구리와 두꺼비는 친구", "author": "아놀드 로벨 글·그림 ; 엄혜숙 옮김", "publisher": "비룡소", "call_no": "808.8-비46ㅂ-1"},
        {"title": "신데렐라 (세계 전래동화)", "author": "샤를 페로 원작 ; 이경혜 글", "publisher": "시공주니어", "call_no": "808.8-시16ㅅ-12"},
        {"title": "혹부리 영감과 은혜 갚은 두꺼비", "author": "서정오 글 ; 한병호 그림", "publisher": "보리", "call_no": "813.8-보94ㅎ"}
    ]

    # 절대경로 및 상대경로 탐색
    possible_paths = [
        SEEDS_FILE_PATH,
        os.path.join("AI","data", "fairytale_seeds.txt"),
        os.path.join("data", "kongjwi_seed.txt")
    ]
    
    target_path = None
    for path in possible_paths:
        if os.path.exists(path):
            target_path = path
            break

    if not target_path:
        # 파일이 없으면 기본값으로 STORY_1 등록
        fallback_map["STORY_1"] = default_books
        return fallback_map

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        # [RECOMMEND_X] 블록 단위 분할
        recommend_sections = re.split(r'\[RECOMMEND_(\d+)\]', content)
        
        for i in range(1, len(recommend_sections), 2):
            story_num = recommend_sections[i]
            story_key = f"STORY_{story_num}"
            section_text = recommend_sections[i + 1]
            
            books = []
            # 줄 단위로 도서 정보 파싱 ("1. 제목 | 저자 | 출판사 | 청구기호")
            lines = section_text.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("["):
                    continue
                
                # "1. 제목 | 저자 | ..." 형태 파싱
                match = re.match(r'^\d+\.\s*(.+)$', line)
                if match:
                    parts = [p.strip() for p in match.group(1).split("|")]
                    if len(parts) >= 4:
                        books.append({
                            "title": parts[0],
                            "author": parts[1],
                            "publisher": parts[2],
                            "call_no": parts[3]
                        })
            
            if books:
                fallback_map[story_key] = books

    except Exception as e:
        print(f"[WARN] 시드 파일 파싱 중 오류 발생, 기본 폴백을 사용합니다: {e}")

    # 비어있는 경우 기본값 세팅
    if "STORY_1" not in fallback_map:
        fallback_map["STORY_1"] = default_books

    return fallback_map


# 모듈 로드 시 시드 데이터 미리 파싱
FALLBACK_MAP = load_fallback_books_from_seeds()


def fetch_recommendations_by_keywords(keywords: list, story_id: str = "STORY_1", limit: int = 5) -> list:
    """
    LLM이 추출한 키워드 리스트를 기반으로 도서관 정보나루 API를 조회하여
    추천 도서 목록(제목, 저자, 출판사, 청구기호) 5권을 반환합니다.
    API 오류나 타임아웃 발생 시, 선택된 동화(story_id)에 맞는 사전 큐레이션 도서를 반환합니다.
    """
    # story_id에 해당하는 폴백 도서 가져오기 (없으면 STORY_1 도서로 대체)
    fallback_books = FALLBACK_MAP.get(story_id, FALLBACK_MAP.get("STORY_1", []))[:limit]

    if not keywords or not DATA4LIBRARY_KEY:
        return fallback_books

    # 키워드 중 첫 번째 키워드를 메인 검색어로 활용
    search_keyword = keywords[0]
    
    url = "http://data4library.kr/api/srchBooks"
    params = {
        "authKey": DATA4LIBRARY_KEY,
        "keyword": search_keyword,
        "pageNo": 1,
        "pageSize": limit,
        "format": "json"
    }

    try:
        # NFR-2 및 ADR-0004 지침에 따라 8초 타임아웃 설정 (재시도 없음, 즉시 폴백)
        response = requests.get(url, params=params, timeout=8)
        
        if response.status_code == 200:
            data = response.json()
            docs = data.get("response", {}).get("docs", [])
            
            books = []
            for item in docs:
                doc = item.get("doc", {})
                books.append({
                    "title": html.escape(doc.get("bookname", "제목 없음")),
                    "author": html.escape(doc.get("authors", "저자 미상")),
                    "publisher": html.escape(doc.get("publisher", "출판사 미상")),
                    "call_no": html.escape(doc.get("class_no", "청구기호 미비치"))
                })
            
            # API에서 결과가 제대로 나왔으면 반환, 비어있으면 해당 동화의 폴백 사용
            return books if books else fallback_books
        else:
            return fallback_books

    except Exception as e:
        # 네트워크 오류, 타임아웃 등 어떤 예외가 발생하더라도 서비스 중단 없이 해당 동화 폴백 반환
        print(f"[WARN] 정보나루 API 호출 실패, {story_id} 폴백 데이터로 대체합니다: {e}")
        return fallback_books

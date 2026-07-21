import os
import requests
import html

# 도서관 정보나루 API 키 (환경변수)
DATA4LIBRARY_KEY = os.getenv("DATA4LIBRARY_KEY")

# 정보나루 API 실패 시 사용할 사전 큐레이션 고정 폴백 5권 (NFR-3, ADR-0004 준수)
FALLBACK_BOOKS = [
    {
        "title": "콩쥐팥쥐",
        "author": "이성실 글 ; 박완서 그림",
        "publisher": "보림",
        "call_no": "813.8-보64ㅋ-2"
    },
    {
        "title": "화요일의 두꺼비",
        "author": "러셀 에릭슨 지음 ; 햇살과나무꾼 옮김",
        "publisher": "사계절",
        "call_no": "843-에296ㅎ"
    },
    {
        "title": "개구리와 두꺼비는 친구",
        "author": "아놀드 로벨 글·그림 ; 엄혜숙 옮김",
        "publisher": "비룡소",
        "call_no": "808.8-비46ㅂ-1"
    },
    {
        "title": "신데렐라 (세계 전래동화)",
        "author": "샤를 페로 원작 ; 이경혜 글",
        "publisher": "시공주니어",
        "call_no": "808.8-시16ㅅ-12"
    },
    {
        "title": "혹부리 영감과 은혜 갚은 두꺼비",
        "author": "서정오 글 ; 한병호 그림",
        "publisher": "보리",
        "call_no": "813.8-보94ㅎ"
    }
]

def fetch_recommendations_by_keywords(keywords: list, limit: int = 5) -> list:
    """
    LLM이 추출한 키워드 리스트를 기반으로 도서관 정보나루 API를 조회하여
    추천 도서 목록(제목, 저자, 출판사, 청구기호) 5권을 반환합니다.
    API 오류나 타임아웃 발생 시 사전 큐레이션 도서(FALLBACK_BOOKS)를 즉시 반환합니다.
    """
    if not keywords or not DATA4LIBRARY_KEY:
        return FALLBACK_BOOKS[:limit]

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
            
            # API에서 결과가 제대로 나왔으면 반환, 비어있으면 폴백 사용
            return books if books else FALLBACK_BOOKS[:limit]
        else:
            return FALLBACK_BOOKS[:limit]

    except Exception as e:
        # 네트워크 오류, 타임아웃 등 어떤 예외가 발생하더라도 서비스 중단 없이 폴백 반환
        print(f"[WARN] 정보나루 API 호출 실패, 폴백 데이터로 대체합니다: {e}")
        return FALLBACK_BOOKS[:limit]

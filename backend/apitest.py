import requests

def test_data4library_api(keyword="두꺼비"):
    # 1. 인증키 세팅 (주소에 직접 넣지 않고 params로 분리하여 깔끔하게 처리)
    auth_key = "myapi"
    
    # 2. 순수한 URL만 지정 (따옴표 안에 공백이나 이상한 특수문자 없도록)
    url = "http://data4library.kr/api/srchBooks"
    
    # 3. 요청 파라미터 세팅
    params = {
        "authKey": auth_key,
        "keyword": keyword,
        "format": "json",
        "pageNo": 1,
        "pageSize": 5
    }
    
    # 4. API 호출
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 도서관 정보나루 API 호출 성공! [{keyword}] 검색 결과:\n")
        docs = data.get('response', {}).get('docs', [])
        
        if not docs:
            print("검색 결과가 없습니다.")
            
        for idx, doc in enumerate(docs, 1):
            book = doc.get('doc', {})
            print(f"{idx}. {book.get('bookname')} / {book.get('authors')} / 청구기호: {book.get('class_no')}")
    else:
        print("❌ 호출 실패 상태 코드:", response.status_code)

if __name__ == "__main__":
    test_data4library_api("두꺼비")

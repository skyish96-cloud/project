from Korpora import Korpora

# 나무위키 텍스트 데이터 다운로드 (자동으로 로컬에 저장됨)
Korpora.fetch("namuwikitext")

# 데이터 로드
from Korpora import NamuwikiTextKorpus

corpus = NamuwikiTextKorpus()

# 제목만 추출하여 Kiwi 사전에 추가
from kiwipiepy import Kiwi

kiwi = Kiwi()

count = 0
for text in corpus.get_all_texts():
    # text.title 은 해당 문서의 제목(고유명사)입니다.
    title = text.title
    kiwi.add_user_word(title, 'NNP')
    count += 1

print(f"{count}개 단어 등록 완료")

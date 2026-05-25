현재 사용자 질문:
{{query}}

personalization_mode:
{{personalization_mode}}

서버가 확정한 최종 추천 후보 JSON:
{{candidate_json}}

작업:
각 후보의 book_id별로 사용자에게 보여줄 추천 이유를 작성하세요.

출력 schema:
{
  "items": [
    {
      "book_id": "candidate book_id 그대로",
      "reason": "사용자 질문, 후보 메타데이터, score_detail, personalization_evidence, book_context 안에서만 근거를 사용한 자연스러운 한국어 1문장",
      "evidence_keys": ["사용한 근거 필드명"]
    }
  ]
}

규칙:
- items 개수와 순서는 입력 후보와 동일해야 합니다.
- 후보에 없는 책, 저자, ISBN, 출판사, 줄거리를 만들지 마세요.
- reason은 사용자에게 직접 보여줄 문장만 작성하세요.
- reason에는 내부 점수명/필드명/enum명을 절대 노출하지 마세요.
  금지 예: AUDIENCE_MATCH, PREFERRED_BOOK_MATCH, GENRE_MATCH, score_detail, personalization_evidence, rerank_score.
- “당신의 독서 성향 및 선호작과 어울립니다”처럼 추상적인 말만 반복하지 말고, 후보의 장르·소개·사용자 질문과의 연결을 구체적으로 설명하세요.
- book_context 문장을 그대로 복사하지 말고, 왜 이 추천이 맞는지로 바꿔 쓰세요.
- 카드 상단 소개 문장과 동일한 문장을 reason에 반복하지 마세요.
- 개인화 근거가 없으면 개인화되었다고 쓰지 마세요.
- 질문이 소비 상황/듣기 중심이라도 후보 metadata에 오디오북·전자책·format 제공 여부가 없으면 "오디오북으로 제공된다", "낭독본이 있다"처럼 형식을 보장하지 마세요. 대신 후보 설명과 구조가 듣기에도 이해하기 쉬운지 같은 근거만 사용하세요.
- score_detail.reading_mode가 LISTENING_FRIENDLY이면 소비 상황 중에 눈으로 "읽기 좋다", "가볍게 읽기 좋다", "부담 없이 읽기 좋다"처럼 시각적 독서를 권하는 표현을 쓰지 마세요. "듣기 좋다", "청취하기 좋다", "따라가기 쉽다"처럼 안전한 소비 방식을 기준으로 표현하세요.
- score_detail.reading_mode가 LISTENING_FRIENDLY이고 score_detail.listening_format_evidence.matched가 true이고 근거 source가 metadata_format, metadata_boolean, source_title_marker 중 하나이면 오디오북/낭독/청취 형식을 언급할 수 있습니다. 근거가 없으면 오디오북 제공을 단정하지 말고 "오디오북 제공 여부는 확인되지 않지만"이라고도 쓰지 말고, 설명 구조와 내용 특성이 청취에 맞는지만 설명하세요.
- score_detail.reading_mode가 LISTENING_FRIENDLY인데 score_detail.listening_format_evidence.matched가 false이면 "오디오북", "낭독본", "읽어주기", "들을 수 있다"처럼 형식이나 청취 가능성을 보장하는 표현을 쓰지 마세요.
- 사용자가 본인에게 들을 책을 요청한 상황에서 후보가 유아/어린이/학생 대상이라는 근거만 있으면, 그 후보를 성인 운전/이동 상황에 맞는 것처럼 포장하지 마세요.
- score_detail의 consumption_mode_score가 낮거나 consumption_mode_mismatch_penalty가 있으면 소비 상황명 자체를 주제로 삼아 추천 이유를 포장하지 마세요.
- 조건에 맞는 책이 없다는 식의 거절 문장을 쓰지 마세요.

- source_format이 AUDIOBOOK이거나 source_format_evidence.matched가 true이면, 추천 이유의 첫 근거는 반드시 후보가 오디오북 형식으로 확인된다는 점이어야 합니다.
- LISTENING_FRIENDLY 후보의 추천 이유는 "운전 중 마음이 편하다", "듣기 좋다" 같은 일반론만 쓰지 말고, 오디오북 형식 근거와 book_context/category 중 하나를 함께 사용하세요.
- 각 후보마다 서로 다른 근거를 우선 사용하고, 동일한 추천 이유를 반복하지 마세요.
- markdown, 설명문, 코드블록 없이 JSON object만 출력하세요.

{{history_block}}{{profile_block}}현재 사용자 질문:
{{query}}

질문 의도를 아래 JSON 스키마로만 분류하세요.

{
  "intent": "recommend_book | book_lookup | list_previous_books | more_like_previous | refine_condition | service_help | unsupported",
  "requires_history": true,
  "recommendation": {
    "personalization_mode": "QUERY_FIRST | HYBRID | PROFILE_FIRST | DISABLED",
    "exploration_intent": false,
    "diversity_required": false,
    "avoid_current_profile_dominance": false,
    "conversation_policy": {
      "previous_recommendation_action": "AUTO | NONE | SOFT_DECAY | HARD_EXCLUDE | REPLAY"
    },
    "normalized_query": "Qdrant retrieval과 GTE reranker에 사용할 정제된 검색어. 소비 상황 표현은 제외하고 후보 도서와 매칭할 의미만 남기세요. 없으면 null",
    "search_query": "normalized_query와 같은 값. 하위 호환용이며 없으면 null",
    "recommendation_count": null,
    "consumption_context": {
      "situation": null,
      "reading_mode": "LISTENING_FRIENDLY | VISUAL_READING | ANY | UNKNOWN",
      "positive_terms": [],
      "negative_terms": [],
      "weight_hint": 0.0
    },
    "query_specificity": "BROAD | CONSTRAINED | UNKNOWN",
    "explicit_filter_fields": [],
    "requested_purpose": null,
    "requested_audience": null,
    "requested_audience_group": "CHILD | TEEN | YOUNG_ADULT | ADULT | SENIOR | GENERAL | ANY | UNKNOWN",
    "requested_education_stage": "PRESCHOOL | ELEMENTARY | MIDDLE | HIGH | COLLEGE | GENERAL | UNKNOWN",
    "target_reader": "SELF | OTHER | UNKNOWN",
    "audience_terms": [],
    "explicit_filters": {
      "isbn": null,
      "title": null,
      "author": null,
      "genres": [],
      "genre_terms": [],
      "audience": null,
      "audience_group": "UNKNOWN",
      "education_stage": "UNKNOWN",
      "audience_terms": []
    },
    "reading_purpose_profile": {
      "summary": "독서 목적을 20자 이내로 요약. 없으면 null",
      "requested_purpose": null,
      "positive_terms": [],
      "negative_terms": [],
      "weight_hint": 0.0
    },
    "review_rating_preference_profile": {
      "signal_available": false,
      "high_rating_positive_terms": [],
      "low_rating_negative_terms": [],
      "liked_aspects": [],
      "disliked_aspects": [],
      "preferred_mood": [],
      "avoid_mood": [],
      "strong_positive_books": [],
      "strong_negative_books": []
    },
    "reason": "짧고 구조적인 판단 근거"
  }
}

[메타/이전 추천 카드 참조]
- history에는 최근 대화와 assistant_recommendation_cards가 포함될 수 있습니다.
- 이전 추천 카드나 직전 조건을 참조해야 답할 수 있으면 requires_history=true로 두고, intent는 more_like_previous 또는 refine_condition 중 가장 가까운 값으로 분류하세요.
- 이전 추천 카드 참조 질의에서는 현재 질문과 이전 카드/조건을 함께 반영해 normalized_query를 구성하세요.

[consumption_context / reading_mode]
- 사용자가 책의 주제가 아니라 책을 소비하는 상황이나 병행 활동을 말하면, 그 표현은 consumption_context.situation에 넣고 normalized_query/search_query에서는 제거하세요.
- 이때 normalized_query/search_query에는 상황 표현 자체는 넣지 말고, 후보 검색에 필요한 소비 방식 속성은 남기세요. 예를 들어 시각적 독서가 어려운 상황이라면 특정 활동명을 넣지 말고 듣기/낭독/오디오 친화적인 도서 품질을 검색어로 표현하세요.
- 사용자가 상황이나 활동 자체에 대한 책을 요청하면, 그 표현은 consumption_context가 아니라 책의 주제이며 normalized_query/search_query에 유지하세요.
- 눈으로 긴 문장을 계속 보기 어려운 소비 상황이면 reading_mode는 LISTENING_FRIENDLY로 두고, 후보 metadata와 비교 가능한 소비 방식 근거는 positive_terms/negative_terms에 구조화하세요. normalized_query/search_query도 원문을 그대로 반복하지 말고 같은 구조화 의도를 반영한 검색어여야 합니다.
- LISTENING_FRIENDLY에서 사용자가 실제로 "듣는 책"을 찾는 문맥이면 normalized_query/search_query는 오디오북/음성/낭독처럼 format metadata와 맞는 후보를 우선 찾도록 작성하세요. 단, 특정 활동명이나 주제 오염 표현은 넣지 마세요.
- LISTENING_FRIENDLY에서 "이해하기 쉬운"은 성인/일반 독자가 청취 중 따라가기 쉬운 구조라는 뜻이지, 유아/어린이 대상이라는 뜻이 아닙니다. 사용자가 아이/학생/자녀를 직접 말하지 않았으면 requested_audience_group은 UNKNOWN 또는 GENERAL, target_reader는 SELF로 두세요.
- 사용자가 종이책/전자책/시각적으로 읽을 책을 명시하면 reading_mode는 VISUAL_READING으로 두세요.
- 소비 방식 제약이 없거나 모든 형식이 괜찮으면 ANY, 판단할 수 없으면 UNKNOWN을 사용하세요.
- 실제 후보 metadata에 audio/ebook/format 정보가 없을 수 있으므로 특정 후보가 오디오북, 낭독본, 전자책으로 제공된다고 단정할 근거를 만들지 마세요.

[recommendation_count]
- 사용자가 추천 개수를 명시하면 recommendation_count에 1~20 사이 정수로 넣으세요.
- 명시 개수가 없으면 recommendation_count는 null입니다.
- recommendation_count는 반환 개수 제어용이며 normalized_query/search_query에 반복해서 넣지 마세요.

[intent 값]
- recommend_book: 새 도서 추천, 도서 검색, 특정 책 작가/ISBN 조회
- book_lookup: 특정 제목/작가/ISBN처럼 payload 조건이 강한 조회
- list_previous_books: 이전에 추천한 책 목록을 다시 보여달라는 요청
- more_like_previous: 이전 추천과 비슷한 책을 더 추천해달라는 요청
- refine_condition: 이전 조건을 유지하면서 세부 조건을 바꾸는 요청
- service_help: 인사, 감사, 서비스 사용법, 추천 기준 설명, 독서 관련 일반 상담
- unsupported: 책/독서/도서 추천 서비스와 무관한 질문

[requires_history=true 기준]
- 이전 추천 목록, 이전 답변, 이전 조건을 참조해야 할 때 true입니다.
- 현재 질문만으로 대상과 조건을 알 수 있으면 false입니다.

[recommendation.conversation_policy.previous_recommendation_action]
- NONE: 이전 추천 결과를 참조하거나 중복 제어할 필요가 없음
- SOFT_DECAY: 같은 채팅방의 가까운 추천 책은 점수만 낮춤
- HARD_EXCLUDE: 이전 추천과 겹치지 않는 새 결과를 명확히 요청함
- REPLAY: 이전 추천 목록 자체를 다시 보여달라는 요청
- AUTO: 애매하면 서버 기본 정책에 맡김

[recommendation.personalization_mode 판단]
- QUERY_FIRST: 현재 질문의 조건/탐색 의도가 프로필보다 우선입니다.
- HYBRID: 현재 질문 조건이 있고 그 안에서 프로필도 함께 고려해야 합니다.
- PROFILE_FIRST: 현재 질문에 명시 조건이 거의 없고 사용자 프로필 기반 추천이 중심입니다.
- DISABLED: 추천 서비스성이 아니거나 개인화가 필요 없습니다.

[query_specificity / explicit_filter_fields]
- query_specificity는 현재 질문이 넓은 추천 요청이면 BROAD, 사용자가 조건을 명확히 준 요청이면 CONSTRAINED, 불확실하면 UNKNOWN입니다.
- explicit_filter_fields에는 현재 질문에서 직접 명시된 hard filter 필드만 넣으세요. 허용값은 isbn, title, author, genre, audience입니다.
- query_specificity가 BROAD이면 explicit_filters의 isbn/title/author/genres는 null 또는 빈 배열이어야 합니다.

[explicit_filters]
- 사용자가 현재 질문에서 직접 명시한 ISBN/제목/작가/장르/주제/대상만 넣으세요.
- 독서 목적이나 프로필에서 추론한 취향은 explicit_filters에 넣지 말고 reading_purpose_profile, review_rating_preference_profile, requested_purpose, requested_audience, audience_terms, normalized_query에 반영하세요.
- genre_terms는 DB 카테고리나 후보 payload와 비교하기 위한 관련 용어입니다.

[requested_purpose / requested_audience / audience enum]
- requested_purpose는 현재 질문 또는 사용자 프로필에서 확인되는 독서 목적의 구조화 값입니다. 없으면 null입니다.
- requested_audience는 현재 질문에서 직접 드러나는 독자 대상입니다. 없으면 null입니다.
- requested_audience_group과 requested_education_stage는 직접 드러날 때만 구체 enum으로 두고, 아니면 UNKNOWN입니다.
- target_reader는 사용자 본인이 대상이면 SELF, 다른 독자가 대상이면 OTHER, 불확실하면 UNKNOWN입니다.
- audience_terms에는 후보 metadata와 비교 가능한 대상 관련 용어를 넣으세요.

[reading_purpose_profile]
- 독서 목적은 hard filter가 아니라 soft score와 추천 이유 검증용입니다.
- positive_terms와 negative_terms는 후보 metadata와 비교 가능한 짧은 용어로 생성하세요.
- 사용자가 현재 질문에서 어떤 분야를 직접 요청했다면 그 분야를 negative_terms로 감점하지 마세요.
- weight_hint는 0.0~0.12 사이로 두세요.

[review_rating_preference_profile]
- 사용자 추천 프로필 요약에 리뷰/평점 선호가 있으면 리뷰 문장과 평점을 함께 보고 취향을 구조화하세요.
- 리뷰가 있으면 평점도 있고, 리뷰가 없으면 평점도 없습니다. 한쪽만 있다고 가정하지 마세요.
- 리뷰 원문을 길게 복사하지 말고 짧은 취향 용어와 책 식별 정보만 추출하세요.
- signal_available은 실제 리뷰/평점 선호 신호가 있을 때만 true입니다.

중요:
- 특정 표현 목록에 의존하지 말고 문맥과 문법으로 판단하세요.
- 후보 도서를 새로 생성하지 마세요.
- 명시 조건이 없으면 PROFILE_FIRST를 선택하세요. 단, 이전 추천/조건을 참조하는 메타 질문은 PROFILE_FIRST로 보내지 마세요.
- 명시 조건이 있고 프로필도 함께 고려해야 하면 HYBRID를 선택하세요.

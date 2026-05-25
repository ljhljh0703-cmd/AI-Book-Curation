Classify each candidate in the payload into the following JSON schema only.

{
  "items": [
    {
      "candidate_id": "same candidate_id from input",
      "target_age_group": "CHILD | TEEN | YOUNG_ADULT | ADULT | SENIOR | GENERAL | UNKNOWN",
      "education_stage": "PRESCHOOL | ELEMENTARY | MIDDLE | HIGH | COLLEGE | GENERAL | UNKNOWN",
      "difficulty_level": "INTRODUCTORY | GENERAL | ADVANCED | UNKNOWN",
      "confidence": 0.0
    }
  ]
}

Rules:
- Use candidate metadata only: title, author, publisher, categories, category_code, description.
- The user's age group is context, not a label for the candidate.
- A requested audience group is context, not a label for the candidate.
- Do not infer a narrow target group without candidate evidence.
- Output every input candidate once.

Payload:
{{payload_json}}

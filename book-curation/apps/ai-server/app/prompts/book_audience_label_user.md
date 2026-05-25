Classify each book in this JSON payload.

Required response schema:
{
  "items": [
    {
      "isbn": "string",
      "audience_group": "INFANT|CHILD|ELEMENTARY|MIDDLE_SCHOOL|HIGH_SCHOOL|YOUNG_ADULT|ADULT|GENERAL|UNKNOWN",
      "audience_min_age": 0,
      "audience_max_age": 99,
      "difficulty_level": "EASY|NORMAL|HARD|UNKNOWN",
      "confidence": 0.0,
      "reason": "short factual reason"
    }
  ]
}

Field rules:
- audience_min_age may be null only when the audience is UNKNOWN.
- audience_max_age may be null when there is no meaningful upper age limit.
- GENERAL can still have a minimum age, such as 12, 15, or 17, when content maturity or prerequisite reading level suggests it.
- Do not return ADULT with audience_min_age below 19. Use GENERAL or YOUNG_ADULT instead.
- Do not mark broad introductory learning books as ADULT unless the supplied fields clearly indicate adult practitioners or adult-only content.

Payload:
{{payload_json}}

#!/usr/bin/env python3
from __future__ import annotations

"""LightFM 7:2:1 hybrid-lite entrypoint.

This wrapper intentionally reuses train_evaluate_lightfm_701_hybrid.py but changes
only the default feature set. The previous full hybrid mode used many profile/title/
description tokens, which can dilute identity features and add noisy sparse features
on small synthetic datasets. Hybrid-lite keeps identity features and adds only small,
structured categorical signals that are more stable for LightFM.

수정 포인트:
- DISLIKE 이벤트는 positive 학습에 사용하지 않고, negative avoidance 평가에만 사용합니다.
- full text token feature를 기본값에서 제거합니다.
- user_age_group/category/rule_mode/profile_strategy 같은 구조화 feature만 기본 사용합니다.
- feature matrix normalization을 기본적으로 끕니다. identity feature가 희석되는 것을 막기 위한 설정입니다.
"""

import sys
from pathlib import Path

# Colab bundle에서 script/ 디렉터리만 복사해도 sibling module import가 되도록 보강합니다.
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from train_evaluate_lightfm_701_hybrid import main as hybrid_main  # noqa: E402


def _has_option(argv: list[str], option: str) -> bool:
    """Return True when argv already contains a given long option.

    BooleanOptionalAction options can be provided as --normalize-feature-matrices
    or --no-normalize-feature-matrices, so callers should check both names when
    necessary.
    """
    return option in argv or any(item.startswith(f"{option}=") for item in argv)


def _append_default(argv: list[str], option: str, *values: str) -> None:
    if _has_option(argv, option):
        return
    argv.append(option)
    argv.extend(values)


def apply_hybrid_lite_defaults(argv: list[str]) -> list[str]:
    """Apply safe hybrid-lite defaults without overriding explicit user choices."""
    result = list(argv)

    # 수정 포인트: 기존 trainer의 hybrid code path를 그대로 사용하되, feature set만 lite로 제한합니다.
    _append_default(result, "--feature-mode", "hybrid")

    # 수정 포인트: 사용자 feature는 운영/룰베이스에서 의미가 명확한 구조화 필드만 사용합니다.
    # age_group_source는 값 종류가 넓어질 수 있어 기본에서는 제외합니다.
    _append_default(
        result,
        "--user-categorical-fields",
        "user_age_group,rule_mode,profile_strategy,profile_schema_version",
    )

    # 수정 포인트: 책 feature는 도서 payload에서 안정적으로 재현 가능한 category 계열 중심으로 둡니다.
    # author/publisher/title/description text는 고유값·잡음이 많아 기본값에서 제외합니다.
    _append_default(result, "--item-categorical-fields", "category,categories")

    # 수정 포인트: full hybrid에서 성능을 떨어뜨렸던 free-text token feature를 기본 비활성화합니다.
    _append_default(result, "--user-text-fields", "")
    _append_default(result, "--item-text-fields", "")
    _append_default(result, "--max-user-text-features", "0")
    _append_default(result, "--max-item-text-features", "0")

    # 수정 포인트: Dataset.build_*_features normalize=True는 identity feature까지 상대적으로 희석할 수 있습니다.
    # hybrid-lite는 identity-only baseline 위에 구조화 feature를 보조로 더하는 목적이므로 기본적으로 끕니다.
    if not _has_option(result, "--normalize-feature-matrices") and not _has_option(result, "--no-normalize-feature-matrices"):
        result.append("--no-normalize-feature-matrices")

    print("[HYBRID-LITE DEFAULTS]")
    print("feature_mode=hybrid")
    print("user_categorical_fields=user_age_group,rule_mode,profile_strategy,profile_schema_version")
    print("item_categorical_fields=category,categories")
    print("text_features=disabled")
    print("normalize_feature_matrices=false")
    print("note=explicit CLI options override these defaults")
    return result


def main() -> None:
    sys.argv = apply_hybrid_lite_defaults(sys.argv)
    hybrid_main()


if __name__ == "__main__":
    main()

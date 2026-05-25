#!/usr/bin/env python3
from __future__ import annotations

"""Export real PostgreSQL user data for LightFM hybrid-lite training.

This script is intentionally read-only. It extracts:
- real_user_events.jsonl: actual user-book interactions
- real_user_features.jsonl: sparse real user profile/category/count features
- real_item_features.jsonl: book category/source/year features

수정 포인트:
- 실사용자는 synthetic persona처럼 63개 행동이 보장되지 않으므로, interaction 부족분을 가짜 행동으로 채우지 않습니다.
- 부족한 사용자 신호는 온보딩/프로필/관심 카테고리/행동 count bucket을 hybrid user feature로 보강합니다.
- 자연어 장르/키워드 목록을 코드에 하드코딩하지 않고 DB의 category_code/option id/hash bucket만 feature로 사용합니다.
"""

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, urlparse, urlunparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

SHELF_EVENT_TYPE_MAP = {
    "WANT_TO_READ": "FAVORITE_ADD",
    "INTERESTED": "FAVORITE_ADD",
    "FAVORITE": "FAVORITE_ADD",
    "READING": "READING_ADD",
    "READ": "READ_ADD",
    "NOT_INTERESTED": "DISLIKE_ADD",
}

ACTION_EVENT_TYPE_MAP = {
    "CLICK": "BOOK_CLICK",
    "BOOK_CLICK": "BOOK_CLICK",
    "SEARCH_CLICK": "BOOK_CLICK",
    "BORROW_CLICK": "BOOK_CLICK",
    "VIEW": "DETAIL_VIEW",
    "DETAIL_VIEW": "DETAIL_VIEW",
    "LIKE": "FAVORITE_ADD",
    "FAVORITE_ADD": "FAVORITE_ADD",
    "READING_ADD": "READING_ADD",
    "READ_ADD": "READ_ADD",
    "DISLIKE": "DISLIKE_ADD",
    "NOT_INTERESTED": "DISLIKE_ADD",
    "DISLIKE_ADD": "DISLIKE_ADD",
    "RATING": "RATING_ADD",
    "RATING_ADD": "RATING_ADD",
    "REVIEW_ADD": "REVIEW_ADD",
    "READ_START": "READING_ADD",
    "READ_FINISH": "READ_ADD",
}

BASE_EVENT_WEIGHTS = {
    "BOOK_CLICK": 1.0,
    "DETAIL_VIEW": 0.8,
    "FAVORITE_ADD": 3.0,
    "READING_ADD": 3.0,
    "READ_ADD": 2.5,
    "RATING_ADD": 3.5,
    "REVIEW_ADD": 4.0,
    "REVIEW_POSITIVE": 4.0,
    "DISLIKE_ADD": 1.0,
}


@dataclass(frozen=True)
class ExportedEvent:
    row: dict[str, Any]
    user_key: str
    item_key: str
    event_type: str
    source_table: str
    source_id: str
    created_at: datetime | None


@dataclass(frozen=True)
class BookFeature:
    book_id: str
    item_key: str
    isbn13: str | None
    features: list[str]
    row: dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export PostgreSQL real user LightFM events and hybrid-lite feature files. Read-only."
    )
    parser.add_argument("--output-events-path", default="data/lightfm/real_user_events.jsonl")
    parser.add_argument("--output-user-features-path", default="data/lightfm/real_user_features.jsonl")
    parser.add_argument("--output-item-features-path", default="data/lightfm/real_item_features.jsonl")
    parser.add_argument("--summary-path", default="data/lightfm/real_lightfm_export.summary.json")
    parser.add_argument("--database-url", default="", help="Falls back to LIGHTFM_TRAINING_DATABASE_URL, DATABASE_URL, DB_URL.")
    parser.add_argument("--db-host", default="", help="Falls back to DB_HOST or POSTGRES_HOST.")
    parser.add_argument("--db-port", default="", help="Falls back to DB_PORT or POSTGRES_PORT. Default: 5432.")
    parser.add_argument("--db-name", default="", help="Falls back to DB_NAME, DB_DATABASE, POSTGRES_DB, or POSTGRES_DATABASE.")
    parser.add_argument("--db-username", default="", help="Falls back to DB_USERNAME, DB_USER, DB_ID, POSTGRES_USER, or POSTGRES_USERNAME.")
    parser.add_argument("--db-password", default="", help="Falls back to DB_PASSWORD, DB_PASS, POSTGRES_PASSWORD, or POSTGRES_PASS.")
    parser.add_argument("--schema", default=os.getenv("DB_SCHEMA", "book"))
    parser.add_argument("--since", default="", help="Optional lower bound timestamp. Example: 2026-05-01T00:00:00+09:00")
    parser.add_argument("--real-weight-multiplier", type=float, default=2.0, help="Real events are usually more trustworthy than synthetic events.")
    parser.add_argument("--hash-buckets", type=int, default=32, help="Bucket count for free-text profile fields. No raw natural-language text is exported as feature by default.")
    parser.add_argument("--min-positive-events-per-user", type=int, default=0, help="0 keeps users with only features. >0 filters event rows by positive count.")
    parser.add_argument("--max-rows-per-source", type=int, default=0, help="Safety limit per source table. 0 means no limit.")
    parser.add_argument("--skip-missing-tables", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-behavior-events", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-shelves", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-actions", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-review-signals", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--env-file", action="append", default=[".env", ".env.local"], help="dotenv file path. Can be repeated.")
    args = parser.parse_args()

    load_env_files(args.env_file)
    schema = validate_identifier(args.schema, "schema")
    since = parse_datetime(args.since) if args.since else None

    conn = connect_to_postgres(args)
    try:
        table_columns = load_table_columns(conn, schema)
        users = fetch_users(conn, schema, table_columns, args)
        categories_by_user = fetch_user_categories(conn, schema, table_columns, args)
        books = fetch_books(conn, schema, table_columns, args)

        events: list[ExportedEvent] = []
        if args.include_shelves:
            events.extend(fetch_shelf_events(conn, schema, table_columns, since, books, args))
        if args.include_actions:
            events.extend(fetch_action_events(conn, schema, table_columns, since, books, args))
        if args.include_behavior_events:
            events.extend(fetch_behavior_events(conn, schema, table_columns, since, books, args))
        if args.include_review_signals:
            events.extend(fetch_review_signal_events(conn, schema, table_columns, since, books, args))

        events = dedupe_events(events)
        if args.min_positive_events_per_user > 0:
            events = filter_events_by_min_positive(events, args.min_positive_events_per_user)

        event_stats_by_user = build_event_stats_by_user(events)
        user_feature_rows = build_user_feature_rows(
            users=users,
            categories_by_user=categories_by_user,
            event_stats_by_user=event_stats_by_user,
            hash_buckets=args.hash_buckets,
        )
        item_feature_rows = build_item_feature_rows(books)

        write_jsonl(Path(args.output_events_path), (event.row for event in events))
        write_jsonl(Path(args.output_user_features_path), user_feature_rows)
        write_jsonl(Path(args.output_item_features_path), item_feature_rows)

        summary = build_summary(
            events=events,
            users=users,
            categories_by_user=categories_by_user,
            books=books,
            user_feature_rows=user_feature_rows,
            item_feature_rows=item_feature_rows,
            args=args,
        )
        write_json(Path(args.summary_path), summary)

        print("[REAL LIGHTFM EXPORT DONE]")
        print(f"events_path={Path(args.output_events_path).resolve()}")
        print(f"user_features_path={Path(args.output_user_features_path).resolve()}")
        print(f"item_features_path={Path(args.output_item_features_path).resolve()}")
        print(f"summary_path={Path(args.summary_path).resolve()}")
        print(f"event_count={summary['event_count']}")
        print(f"user_feature_count={summary['user_feature_row_count']}")
        print(f"item_feature_count={summary['item_feature_row_count']}")
        print(f"event_type_counts={summary['event_type_counts']}")
    finally:
        conn.close()


def load_env_files(paths: Sequence[str]) -> None:
    if load_dotenv is None:
        return
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if path.exists():
            load_dotenv(dotenv_path=path, override=False)


def connect_to_postgres(args: argparse.Namespace):
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("psycopg is required. Install with: python -m pip install 'psycopg[binary]>=3.1,<4'") from exc

    raw_url = first_non_empty(
        args.database_url,
        os.getenv("LIGHTFM_TRAINING_DATABASE_URL"),
        os.getenv("DATABASE_URL"),
        os.getenv("DB_URL"),
    )
    username = first_non_empty(
        args.db_username,
        os.getenv("DB_USERNAME"),
        os.getenv("DB_USER"),
        os.getenv("DB_ID"),
        os.getenv("POSTGRES_USER"),
        os.getenv("POSTGRES_USERNAME"),
    )
    password = first_non_empty(
        args.db_password,
        os.getenv("DB_PASSWORD"),
        os.getenv("DB_PASS"),
        os.getenv("POSTGRES_PASSWORD"),
        os.getenv("POSTGRES_PASS"),
    )

    if raw_url:
        conninfo = normalize_database_url(raw_url, username, password)
        return psycopg.connect(conninfo=conninfo, connect_timeout=15)

    host = first_non_empty(args.db_host, os.getenv("DB_HOST"), os.getenv("POSTGRES_HOST"))
    port = first_non_empty(args.db_port, os.getenv("DB_PORT"), os.getenv("POSTGRES_PORT"), "5432")
    dbname = first_non_empty(
        args.db_name,
        os.getenv("DB_NAME"),
        os.getenv("DB_DATABASE"),
        os.getenv("POSTGRES_DB"),
        os.getenv("POSTGRES_DATABASE"),
    )

    missing = []
    if not host:
        missing.append("DB_HOST")
    if not dbname:
        missing.append("DB_NAME")
    if not username:
        missing.append("DB_USERNAME or DB_ID")
    if not password:
        missing.append("DB_PASSWORD")
    if missing:
        raise SystemExit(
            "Database connection info is required. Set DB_URL or set split DB variables: "
            + ", ".join(missing)
        )

    return psycopg.connect(
        host=host,
        port=int(port),
        dbname=dbname,
        user=username,
        password=password,
        connect_timeout=15,
    )


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def normalize_database_url(raw_url: str, username: str | None, password: str | None) -> str:
    url = raw_url.strip()
    if url.startswith("jdbc:postgresql://"):
        url = "postgresql://" + url.removeprefix("jdbc:postgresql://")
    # SQLAlchemy style URLs are not valid psycopg conninfo URIs.
    # Keep this exporter usable with values commonly used by application env files.
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url.removeprefix("postgresql+psycopg://")
    if not url.startswith(("postgresql://", "postgres://")):
        return url
    if not username and not password:
        return url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    userinfo = ""
    if username:
        userinfo = quote(username, safe="")
        if password:
            userinfo += f":{quote(password, safe='')}"
        userinfo += "@"
    netloc = f"{userinfo}{host}{port}"
    return urlunparse(("postgresql", netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def validate_identifier(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not SAFE_IDENTIFIER.match(text):
        raise SystemExit(f"Invalid {label}: {value}")
    return text


def load_table_columns(conn, schema: str) -> dict[str, set[str]]:
    sql = """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = %s
    """
    result: dict[str, set[str]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute(sql, (schema,))
        for table_name, column_name in cur.fetchall():
            result[str(table_name)].add(str(column_name))
    return dict(result)


def has_table(table_columns: Mapping[str, set[str]], table: str) -> bool:
    return table in table_columns


def column_list(table_columns: Mapping[str, set[str]], table: str, wanted: Sequence[str]) -> list[str]:
    existing = table_columns.get(table, set())
    return [column for column in wanted if column in existing]


def require_table(table_columns: Mapping[str, set[str]], table: str, args: argparse.Namespace) -> bool:
    if has_table(table_columns, table):
        return True
    message = f"Missing table: {table}"
    if args.skip_missing_tables:
        print(f"[WARN] {message}; skipping")
        return False
    raise SystemExit(message)


def limit_clause(args: argparse.Namespace) -> str:
    return f" LIMIT {int(args.max_rows_per_source)}" if args.max_rows_per_source and args.max_rows_per_source > 0 else ""


def fetch_users(conn, schema: str, table_columns: Mapping[str, set[str]], args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    if not require_table(table_columns, "users", args):
        return {}
    profile_columns = column_list(
        table_columns,
        "user_profiles",
        [
            "birth_date",
            "resident_gender_digit",
            "reader_type_option_id",
            "reading_purpose",
            "profile_summary",
            "onboarding_completed",
            "preferred_radius_km",
            "updated_at",
        ],
    )
    profile_select = ", ".join(f"up.{column} AS profile_{column}" for column in profile_columns)
    if profile_select:
        profile_select = ", " + profile_select
    join_profile = f"LEFT JOIN {schema}.user_profiles up ON up.user_id = u.id" if has_table(table_columns, "user_profiles") else ""
    sql = f"""
        SELECT u.id::text AS user_id, u.status, u.created_at, u.updated_at {profile_select}
        FROM {schema}.users u
        {join_profile}
        WHERE COALESCE(u.status, 'ACTIVE') <> 'DELETED'
        ORDER BY u.created_at, u.id
        {limit_clause(args)}
    """
    result: dict[str, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(sql)
        for record in rows_as_dicts(cur):
            user_id = str(record.get("user_id") or "").strip()
            if not user_id:
                continue
            user_key = real_user_key(user_id)
            result[user_key] = {"user_key": user_key, "user_id": user_id, **record}
    return result


def fetch_user_categories(conn, schema: str, table_columns: Mapping[str, set[str]], args: argparse.Namespace) -> dict[str, list[dict[str, Any]]]:
    if not require_table(table_columns, "user_interest_categories", args):
        return {}
    join_category = f"LEFT JOIN {schema}.book_categories bc ON bc.category_code = uic.category_code" if has_table(table_columns, "book_categories") else ""
    category_name_select = ", bc.category_name, bc.parent_category_code" if join_category else ", NULL::text AS category_name, NULL::text AS parent_category_code"
    sql = f"""
        SELECT uic.user_id::text AS user_id, uic.category_code, uic.weight, uic.source {category_name_select}
        FROM {schema}.user_interest_categories uic
        {join_category}
        ORDER BY uic.user_id, uic.weight DESC, uic.category_code
        {limit_clause(args)}
    """
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(sql)
        for record in rows_as_dicts(cur):
            user_key = real_user_key(record.get("user_id"))
            if user_key:
                result[user_key].append(record)
    return dict(result)


def fetch_books(conn, schema: str, table_columns: Mapping[str, set[str]], args: argparse.Namespace) -> dict[str, BookFeature]:
    if not require_table(table_columns, "books", args):
        return {}
    wanted = ["id", "isbn13", "title", "author", "publisher", "publication_year", "category_code", "language", "source", "raw_json", "created_at", "updated_at"]
    select_cols = column_list(table_columns, "books", wanted)
    sql = f"SELECT {', '.join(select_cols)} FROM {schema}.books ORDER BY id {limit_clause(args)}"
    result: dict[str, BookFeature] = {}
    with conn.cursor() as cur:
        cur.execute(sql)
        for record in rows_as_dicts(cur):
            book_id = as_text(record.get("id"))
            if not book_id:
                continue
            isbn13 = normalize_isbn(record.get("isbn13"))
            item_key = isbn13 or book_id
            features = build_item_features(record)
            row = {
                "book_id": book_id,
                "item_id": item_key,
                "isbn13": isbn13,
                "category": record.get("category_code"),
                "category_code": record.get("category_code"),
                "publication_year": record.get("publication_year"),
                "source": record.get("source"),
                "language": record.get("language"),
                "features": features,
            }
            result[book_id] = BookFeature(book_id=book_id, item_key=item_key, isbn13=isbn13, features=features, row=compact(row))
    return result


def fetch_shelf_events(conn, schema: str, table_columns: Mapping[str, set[str]], since: datetime | None, books: Mapping[str, BookFeature], args: argparse.Namespace) -> list[ExportedEvent]:
    if not require_table(table_columns, "user_book_shelves", args):
        return []
    where = "WHERE 1=1"
    params: list[Any] = []
    if since and "updated_at" in table_columns.get("user_book_shelves", set()):
        where += " AND ubs.updated_at >= %s"
        params.append(since)
    sql = f"""
        SELECT ubs.id::text AS source_id, ubs.user_id::text AS user_id, ubs.book_id::text AS book_id,
               ubs.shelf_type, ubs.review_content, ubs.review_rating,
               COALESCE(ubs.completed_at, ubs.updated_at, ubs.created_at) AS created_at,
               b.isbn13, b.category_code, b.title, b.author, b.publisher
        FROM {schema}.user_book_shelves ubs
        LEFT JOIN {schema}.books b ON b.id = ubs.book_id
        {where}
        ORDER BY COALESCE(ubs.updated_at, ubs.created_at), ubs.id
        {limit_clause(args)}
    """
    events: list[ExportedEvent] = []
    with conn.cursor() as cur:
        cur.execute(sql, params)
        for record in rows_as_dicts(cur):
            shelf_type = as_text(record.get("shelf_type")).upper()
            event_type = SHELF_EVENT_TYPE_MAP.get(shelf_type)
            if not event_type:
                continue
            events.append(make_event(record, event_type, "user_book_shelves", args.real_weight_multiplier, books))
            if record.get("review_rating") is not None:
                events.append(make_event(record, "RATING_ADD", "user_book_shelves", args.real_weight_multiplier, books, source_id_suffix="rating"))
            if as_text(record.get("review_content")):
                events.append(make_event(record, "REVIEW_ADD", "user_book_shelves", args.real_weight_multiplier, books, source_id_suffix="review"))
    return events


def fetch_action_events(conn, schema: str, table_columns: Mapping[str, set[str]], since: datetime | None, books: Mapping[str, BookFeature], args: argparse.Namespace) -> list[ExportedEvent]:
    if not require_table(table_columns, "user_book_actions", args):
        return []
    where = "WHERE 1=1"
    params: list[Any] = []
    if since and "created_at" in table_columns.get("user_book_actions", set()):
        where += " AND uba.created_at >= %s"
        params.append(since)
    sql = f"""
        SELECT uba.id::text AS source_id, uba.user_id::text AS user_id, uba.book_id::text AS book_id,
               uba.action_type, uba.rating, uba.source, uba.created_at,
               b.isbn13, b.category_code, b.title, b.author, b.publisher
        FROM {schema}.user_book_actions uba
        LEFT JOIN {schema}.books b ON b.id = uba.book_id
        {where}
        ORDER BY uba.created_at, uba.id
        {limit_clause(args)}
    """
    events: list[ExportedEvent] = []
    with conn.cursor() as cur:
        cur.execute(sql, params)
        for record in rows_as_dicts(cur):
            action_type = as_text(record.get("action_type")).upper()
            event_type = ACTION_EVENT_TYPE_MAP.get(action_type)
            if not event_type:
                continue
            events.append(make_event(record, event_type, "user_book_actions", args.real_weight_multiplier, books))
    return events


def fetch_behavior_events(conn, schema: str, table_columns: Mapping[str, set[str]], since: datetime | None, books: Mapping[str, BookFeature], args: argparse.Namespace) -> list[ExportedEvent]:
    if not require_table(table_columns, "user_behavior_events", args):
        return []
    where = "WHERE ube.book_id IS NOT NULL"
    params: list[Any] = []
    if since and "created_at" in table_columns.get("user_behavior_events", set()):
        where += " AND ube.created_at >= %s"
        params.append(since)
    sql = f"""
        SELECT ube.id::text AS source_id, ube.user_id::text AS user_id, ube.book_id::text AS book_id,
               ube.event_type, ube.source, ube.rank, ube.score, ube.created_at,
               b.isbn13, b.category_code, b.title, b.author, b.publisher
        FROM {schema}.user_behavior_events ube
        LEFT JOIN {schema}.books b ON b.id = ube.book_id
        {where}
        ORDER BY ube.created_at, ube.id
        {limit_clause(args)}
    """
    events: list[ExportedEvent] = []
    with conn.cursor() as cur:
        cur.execute(sql, params)
        for record in rows_as_dicts(cur):
            event_type = as_text(record.get("event_type")).upper()
            if event_type in {"RECOMMENDATION_IMPRESSION", "SEARCH_QUERY", "FAVORITE_REMOVE", "DISLIKE_REMOVE"}:
                continue
            if event_type not in BASE_EVENT_WEIGHTS:
                continue
            events.append(make_event(record, event_type, "user_behavior_events", args.real_weight_multiplier, books))
    return events


def fetch_review_signal_events(conn, schema: str, table_columns: Mapping[str, set[str]], since: datetime | None, books: Mapping[str, BookFeature], args: argparse.Namespace) -> list[ExportedEvent]:
    if not require_table(table_columns, "user_review_preference_signals", args):
        return []
    where = "WHERE COALESCE(sig.active, TRUE) = TRUE"
    params: list[Any] = []
    if since and "updated_at" in table_columns.get("user_review_preference_signals", set()):
        where += " AND sig.updated_at >= %s"
        params.append(since)
    sql = f"""
        SELECT sig.id::text AS source_id, sig.user_id::text AS user_id, sig.book_id::text AS book_id,
               sig.rating, sig.overall_sentiment, sig.sentiment_score, sig.confidence,
               COALESCE(sig.analyzed_at, sig.updated_at, sig.created_at) AS created_at,
               b.isbn13, b.category_code, b.title, b.author, b.publisher
        FROM {schema}.user_review_preference_signals sig
        LEFT JOIN {schema}.books b ON b.id = sig.book_id
        {where}
        ORDER BY COALESCE(sig.analyzed_at, sig.updated_at, sig.created_at), sig.id
        {limit_clause(args)}
    """
    events: list[ExportedEvent] = []
    with conn.cursor() as cur:
        cur.execute(sql, params)
        for record in rows_as_dicts(cur):
            rating = parse_float(record.get("rating"))
            sentiment = as_text(record.get("overall_sentiment")).lower()
            if rating is not None and rating <= 2.0 or sentiment == "negative":
                event_type = "DISLIKE_ADD"
            else:
                event_type = "REVIEW_POSITIVE"
            events.append(make_event(record, event_type, "user_review_preference_signals", args.real_weight_multiplier, books))
    return events


def make_event(record: Mapping[str, Any], event_type: str, source_table: str, real_weight_multiplier: float, books: Mapping[str, BookFeature], source_id_suffix: str = "") -> ExportedEvent:
    raw_user_id = as_text(record.get("user_id"))
    raw_book_id = as_text(record.get("book_id"))
    book = books.get(raw_book_id)
    isbn13 = normalize_isbn(record.get("isbn13")) or (book.isbn13 if book else None)
    item_key = isbn13 or raw_book_id
    user_key = real_user_key(raw_user_id)
    created_at = parse_datetime(record.get("created_at"))
    source_id = as_text(record.get("source_id"))
    if source_id_suffix:
        source_id = f"{source_id}:{source_id_suffix}"
    base_weight = BASE_EVENT_WEIGHTS.get(event_type, 1.0)
    final_weight = base_weight * max(0.0, real_weight_multiplier)
    row = {
        "user_key": user_key,
        "user_id": user_key,
        "real_user_id": raw_user_id,
        "item_id": item_key,
        "book_id": raw_book_id,
        "isbn13": isbn13,
        "event_type": event_type,
        "source_dataset": "real",
        "source_table": source_table,
        "source_id": source_id,
        "base_weight": base_weight,
        "weight": final_weight,
        "final_weight": final_weight,
        "created_at": created_at.isoformat() if created_at else None,
        "category": record.get("category_code") or (book.row.get("category_code") if book else None),
        "category_code": record.get("category_code") or (book.row.get("category_code") if book else None),
        "rating": record.get("rating") or record.get("review_rating"),
        "overall_sentiment": record.get("overall_sentiment"),
        "real_profile_feature_source": "db_export",
    }
    return ExportedEvent(row=compact(row), user_key=user_key, item_key=item_key, event_type=event_type, source_table=source_table, source_id=source_id, created_at=created_at)


def build_user_feature_rows(
    *,
    users: Mapping[str, dict[str, Any]],
    categories_by_user: Mapping[str, list[dict[str, Any]]],
    event_stats_by_user: Mapping[str, Counter[str]],
    hash_buckets: int,
) -> list[dict[str, Any]]:
    all_user_keys = sorted(set(users) | set(categories_by_user) | set(event_stats_by_user))
    rows: list[dict[str, Any]] = []
    for user_key in all_user_keys:
        profile = dict(users.get(user_key, {}))
        categories = list(categories_by_user.get(user_key, []))
        stats = event_stats_by_user.get(user_key, Counter())
        birth_date = profile.get("profile_birth_date") or profile.get("birth_date")
        age_group = age_group_from_birth_date(birth_date)
        reader_type_option_id = as_text(profile.get("profile_reader_type_option_id"))
        reading_purpose = profile.get("profile_reading_purpose")
        profile_summary = profile.get("profile_profile_summary")
        radius = parse_float(profile.get("profile_preferred_radius_km"))
        features: list[str] = [
            "u_cat:user_source:real",
            f"u_cat:onboarding_completed:{bool(profile.get('profile_onboarding_completed'))}",
        ]
        if age_group:
            features.append(f"u_cat:user_age_group:{age_group}")
        if reader_type_option_id:
            features.append(f"u_cat:reader_type_option_id:{reader_type_option_id}")
        if radius is not None:
            features.append(f"u_cat:preferred_radius_bucket:{numeric_bucket(radius, [1, 3, 5, 10, 20, 50])}")
        if as_text(reading_purpose):
            features.append("u_cat:reading_purpose_present:true")
            features.append(f"u_cat:reading_purpose_hash_bucket:{hash_bucket(reading_purpose, hash_buckets)}")
        if as_text(profile_summary):
            features.append("u_cat:profile_summary_present:true")
            features.append(f"u_cat:profile_summary_hash_bucket:{hash_bucket(profile_summary, hash_buckets)}")
        for category in categories:
            code = as_text(category.get("category_code"))
            if code:
                features.append(f"u_cat:preferred_category_code:{code}")
            source = as_text(category.get("source"))
            if source:
                features.append(f"u_cat:preferred_category_source:{source}")
            parent = as_text(category.get("parent_category_code"))
            if parent:
                features.append(f"u_cat:preferred_parent_category_code:{parent}")
        total_positive = sum(count for event_type, count in stats.items() if event_type != "DISLIKE_ADD")
        total_dislike = stats.get("DISLIKE_ADD", 0)
        features.append(f"u_cat:positive_event_count_bucket:{count_bucket(total_positive)}")
        features.append(f"u_cat:dislike_event_count_bucket:{count_bucket(total_dislike)}")
        for event_type in sorted(stats):
            features.append(f"u_cat:has_event_type:{event_type}")
        rows.append(
            compact(
                {
                    "user_key": user_key,
                    "user_id": user_key,
                    "real_user_id": profile.get("user_id") or user_key.removeprefix("real_user:"),
                    "user_age_group": age_group,
                    "reader_type_option_id": reader_type_option_id,
                    "onboarding_completed": profile.get("profile_onboarding_completed"),
                    "preferred_category_codes": [as_text(item.get("category_code")) for item in categories if as_text(item.get("category_code"))],
                    "positive_event_count": total_positive,
                    "dislike_event_count": total_dislike,
                    "features": sorted(set(features)),
                }
            )
        )
    return rows


def build_item_feature_rows(books: Mapping[str, BookFeature]) -> list[dict[str, Any]]:
    return [book.row for book in sorted(books.values(), key=lambda value: value.book_id)]


def build_item_features(record: Mapping[str, Any]) -> list[str]:
    features: list[str] = ["i_cat:item_source:real_db"]
    category_code = as_text(record.get("category_code"))
    if category_code:
        features.append(f"i_cat:category_code:{category_code}")
        features.append(f"i_cat:category_prefix:{category_code[:1]}")
        if len(category_code) >= 2:
            features.append(f"i_cat:category_prefix2:{category_code[:2]}")
    publication_year = parse_int(record.get("publication_year"))
    if publication_year:
        features.append(f"i_cat:publication_year_bucket:{year_bucket(publication_year)}")
    source = as_text(record.get("source"))
    if source:
        features.append(f"i_cat:book_source:{source}")
    language = as_text(record.get("language"))
    if language:
        features.append(f"i_cat:language:{language}")
    return sorted(set(features))


def build_event_stats_by_user(events: Sequence[ExportedEvent]) -> dict[str, Counter[str]]:
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        result[event.user_key][event.event_type] += 1
    return dict(result)


def dedupe_events(events: Sequence[ExportedEvent]) -> list[ExportedEvent]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[ExportedEvent] = []
    for event in sorted(events, key=lambda value: (value.user_key, value.item_key, value.event_type, value.created_at or datetime.min.replace(tzinfo=timezone.utc), value.source_table, value.source_id)):
        key = (event.user_key, event.item_key, event.event_type, event.source_table)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def filter_events_by_min_positive(events: Sequence[ExportedEvent], minimum: int) -> list[ExportedEvent]:
    counts: Counter[str] = Counter()
    for event in events:
        if event.event_type != "DISLIKE_ADD":
            counts[event.user_key] += 1
    keep = {user_key for user_key, count in counts.items() if count >= minimum}
    return [event for event in events if event.user_key in keep]


def build_summary(
    *,
    events: Sequence[ExportedEvent],
    users: Mapping[str, dict[str, Any]],
    categories_by_user: Mapping[str, list[dict[str, Any]]],
    books: Mapping[str, BookFeature],
    user_feature_rows: Sequence[Mapping[str, Any]],
    item_feature_rows: Sequence[Mapping[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_count": len(events),
        "user_count_in_events": len({event.user_key for event in events}),
        "item_count_in_events": len({event.item_key for event in events}),
        "user_profile_row_count": len(users),
        "user_feature_row_count": len(user_feature_rows),
        "item_feature_row_count": len(item_feature_rows),
        "book_row_count": len(books),
        "interest_category_user_count": len(categories_by_user),
        "event_type_counts": dict(Counter(event.event_type for event in events)),
        "source_table_counts": dict(Counter(event.source_table for event in events)),
        "real_weight_multiplier": args.real_weight_multiplier,
        "hash_buckets": args.hash_buckets,
        "notes": [
            "Events are real user interactions only; no fake interactions are created for sparse users.",
            "User/item feature files are meant for hybrid-lite LightFM training.",
            "Do not commit generated JSONL files to Git.",
        ],
    }


def rows_as_dicts(cur) -> list[dict[str, Any]]:
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(compact(dict(row)), ensure_ascii=False, default=json_default) + "\n")


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, default=json_default)


def real_user_key(value: Any) -> str:
    text = as_text(value)
    return f"real_user:{text}" if text else ""


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_isbn(value: Any) -> str | None:
    text = re.sub(r"\D", "", as_text(value))
    if len(text) == 13:
        return text
    return None


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = as_text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def age_group_from_birth_date(value: Any) -> str | None:
    parsed = None
    if isinstance(value, date):
        parsed = value
    else:
        text = as_text(value)
        if text:
            try:
                parsed = date.fromisoformat(text[:10])
            except ValueError:
                parsed = None
    if not parsed:
        return None
    today = date.today()
    age = today.year - parsed.year - ((today.month, today.day) < (parsed.month, parsed.day))
    if age <= 12:
        return "CHILD"
    if age <= 18:
        return "TEEN"
    if age <= 29:
        return "YOUNG_ADULT"
    if age <= 64:
        return "ADULT"
    return "SENIOR"


def hash_bucket(value: Any, bucket_count: int) -> str:
    text = as_text(value)
    if not text:
        return "none"
    count = max(1, int(bucket_count))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return str(int(digest[:12], 16) % count)


def numeric_bucket(value: float, thresholds: Sequence[float]) -> str:
    for threshold in thresholds:
        if value <= threshold:
            return f"le_{threshold:g}"
    return f"gt_{thresholds[-1]:g}" if thresholds else "unknown"


def count_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 3:
        return "2_3"
    if count <= 5:
        return "4_5"
    if count <= 10:
        return "6_10"
    if count <= 20:
        return "11_20"
    return "gt_20"


def year_bucket(year: int) -> str:
    if year < 1980:
        return "before_1980"
    decade = (year // 10) * 10
    return f"{decade}s"


def compact(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None and value != "" and value != []}


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    main()

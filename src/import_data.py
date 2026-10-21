"""Create the MongoDB schema and import the cleaned EDA outputs.

The importer expects step 3 files in ``outputs/eda`` and the filtered movie
table produced by step 7. It is deliberately idempotent: movie documents and
rating events are upserted instead of being duplicated on every run.
"""

import argparse
import ast
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pymongo import ReplaceOne

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "outputs" / "eda"

# Make the project package importable both as a module and as a direct script.
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from DbConnector import DbConnector


def _stage(name, function):
    started = time.perf_counter()
    print(f"[START] {name}")
    result = function()
    print(f"[DONE] {name} ({time.perf_counter() - started:.2f}s)")
    return result


def _find_output(output_dir, pattern, description):
    matches = sorted(output_dir.glob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one {description} matching {pattern!r} in "
            f"{output_dir}, found {len(matches)}."
        )
    return matches[0]


def _read_output(path):
    return pd.read_csv(path, dtype="string", keep_default_na=False, na_filter=False)


def _parse_nested(value):
    if value is None or pd.isna(value) or str(value).strip() in {"", "[]", "{}"}:
        return []
    try:
        parsed = ast.literal_eval(str(value))
    except (SyntaxError, ValueError):
        try:
            parsed = json.loads(str(value))
        except (json.JSONDecodeError, TypeError):
            return []
    return parsed if isinstance(parsed, list) else []


def _int_or_none(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else None


def _float_or_none(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_or_none(value):
    if value is None or value == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().replace(tzinfo=timezone.utc)


def _clean_value(value):
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().replace(tzinfo=timezone.utc)
    if isinstance(value, dict):
        return {key: _clean_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _nested_items(value, fields):
    items = []
    for item in _parse_nested(value):
        if not isinstance(item, dict):
            continue
        normalized = {}
        for source, target in fields.items():
            normalized[target] = _clean_value(item.get(source))
        items.append(normalized)
    return items


def _load_tables(output_dir):
    files = {
        "movies": _find_output(
            output_dir, "step_7_movies_metadata.csv", "step 7 movie output"
        ),
        "credits": _find_output(output_dir, "step_3_credits*.csv", "cleaned credits"),
        "keywords": _find_output(
            output_dir, "step_3_keywords*.csv", "cleaned keywords"
        ),
        "links": _find_output(output_dir, "step_3_links*.csv", "cleaned links"),
        "ratings": _find_output(output_dir, "step_3_ratings*.csv", "cleaned ratings"),
    }
    print("Input files:")
    for name, path in files.items():
        print(f"  - {name}: {path}")
    return {name: _read_output(path) for name, path in files.items()}


def _create_schema(database):
    for name in ("movies", "ratings"):
        if name not in database.list_collection_names():
            database.create_collection(name)

    database.movies.create_index("tmdb_id", unique=True)
    database.movies.create_index(
        "imdb_id",
        unique=True,
        partialFilterExpression={"imdb_id": {"$type": "string"}},
    )
    database.movies.create_index(
        "movie_lens_id",
        unique=True,
        partialFilterExpression={"movie_lens_id": {"$type": ["int", "long"]}},
    )
    database.movies.create_index([("overview", "text"), ("tagline", "text")])
    database.ratings.create_index("movie_lens_id")
    database.ratings.create_index("user_id")
    database.ratings.create_index([("user_id", 1), ("movie_lens_id", 1)])


def _related_indexes(frame, id_column):
    return {
        _int_or_none(row[id_column]): row
        for _, row in frame.iterrows()
        if _int_or_none(row[id_column]) is not None
    }


def _valid_links(frame):
    links = frame.copy()
    links["movie_lens_id"] = links["movieId"].map(_int_or_none)
    links["tmdb_id"] = links["tmdbId"].map(_int_or_none)
    links = links.dropna(subset=["movie_lens_id", "tmdb_id"])
    return links[
        ~links["movie_lens_id"].duplicated(keep=False)
        & ~links["tmdb_id"].duplicated(keep=False)
    ]


def _rating_aggregates(ratings, links):
    rating_data = ratings.copy()
    rating_data["movie_lens_id"] = rating_data["movieId"].map(_int_or_none)
    rating_data["user_id"] = rating_data["userId"].map(_int_or_none)
    rating_data["rating_value"] = rating_data["rating"].map(_float_or_none)
    link_data = _valid_links(links)
    rating_data = rating_data.dropna(subset=["movie_lens_id", "rating_value"])
    joined = rating_data.merge(
        link_data[["movie_lens_id", "tmdb_id"]], on="movie_lens_id", how="inner"
    )
    return (
        joined.groupby("tmdb_id")["rating_value"]
        .agg(rating_average="mean", rating_count="count")
        .to_dict("index")
    )


def _movie_document(row, credits, keywords, links, aggregates):
    tmdb_id = _int_or_none(row.get("id"))
    if tmdb_id is None:
        return None
    link = links.get(tmdb_id)
    movie_lens_id = _int_or_none(link["movieId"]) if link is not None else None
    credit = credits.get(tmdb_id, {})
    keyword = keywords.get(tmdb_id, {})
    document = {
        "_id": tmdb_id,
        "tmdb_id": tmdb_id,
        "imdb_id": _clean_value(row.get("imdb_id")) or None,
        "movie_lens_id": movie_lens_id,
        "title": _clean_value(row.get("title")) or None,
        "original_title": _clean_value(row.get("original_title")) or None,
        "original_language": _clean_value(row.get("original_language")) or None,
        "status": _clean_value(row.get("status")) or "Unknown",
        "adult": _clean_value(row.get("adult")) == "True",
        "video": _clean_value(row.get("video")) == "True",
        "release_date": _date_or_none(row.get("release_date")),
        "release_year": _int_or_none(row.get("release_year")),
        "release_month": _int_or_none(row.get("release_month")),
        "release_decade": _clean_value(row.get("release_decade")) or None,
        "budget": _float_or_none(row.get("budget")),
        "revenue": _float_or_none(row.get("revenue")),
        "runtime": _float_or_none(row.get("runtime")),
        "popularity": _float_or_none(row.get("popularity")),
        "vote_average": _float_or_none(row.get("vote_average")),
        "vote_count": _float_or_none(row.get("vote_count")),
        "rating_average": aggregates.get(tmdb_id, {}).get("rating_average"),
        "rating_count": aggregates.get(tmdb_id, {}).get("rating_count"),
        "overview": _clean_value(row.get("overview")) or None,
        "tagline": _clean_value(row.get("tagline")) or None,
        "homepage": _clean_value(row.get("homepage")) or None,
        "poster_path": _clean_value(row.get("poster_path")) or None,
        "genres": _nested_items(
            row.get("genres"),
            {"id": "id", "name": "name"},
        ),
        "production_companies": _nested_items(
            row.get("production_companies"),
            {"id": "id", "name": "name"},
        ),
        "production_countries": _nested_items(
            row.get("production_countries"),
            {"iso_3166_1": "iso_3166_1", "name": "name"},
        ),
        "spoken_languages": _nested_items(
            row.get("spoken_languages"),
            {"iso_639_1": "iso_639_1", "name": "name"},
        ),
        "keywords": _nested_items(keyword.get("keywords", "[]"), {"id": "id", "name": "name"}),
        "cast": _nested_items(
            credit.get("cast", "[]"),
            {
                "id": "person_id",
                "name": "name",
                "character": "character",
                "order": "order",
                "gender": "gender",
                "profile_path": "profile_path",
            },
        ),
        "crew": _nested_items(
            credit.get("crew", "[]"),
            {
                "id": "person_id",
                "name": "name",
                "department": "department",
                "job": "job",
                "gender": "gender",
                "profile_path": "profile_path",
            },
        ),
    }
    return _clean_value(document)


def _rating_operations(database, ratings, links, movie_ids, chunk_size=100_000, write_chunk_size=5_000):
    """Build and write MovieLens rating documents in chunks to keep memory under control."""
    link_data = _valid_links(links)
    if link_data.empty:
        print("[WARN] No valid links found between MovieLens IDs and TMDB IDs.")
        return 0, 0

    valid_lookup = (
        link_data[["movie_lens_id", "tmdb_id"]]
        .dropna()
        .drop_duplicates(subset=["movie_lens_id"])
        .set_index("movie_lens_id")["tmdb_id"]
        .to_dict()
    )
    movie_ids = set(movie_ids)
    existing_rating_ids = set(database.ratings.distinct("_id"))
    total_rows = len(ratings)
    processed = 0
    skipped = 0
    pending_operations = []
    start_time = time.perf_counter()

    print(f"[INFO] Starting rating import with chunk_size={chunk_size}, write_chunk_size={write_chunk_size}.")
    print(f"[INFO] Total rating rows to inspect: {total_rows}")
    print(f"[INFO] Existing rating ids already in MongoDB: {len(existing_rating_ids)}")

    for chunk_index, start in enumerate(range(0, total_rows, chunk_size), start=1):
        chunk = ratings.iloc[start : start + chunk_size].copy()
        chunk_rows = len(chunk)
        chunk_processed = 0
        chunk_skipped = 0

        chunk["movie_lens_id"] = chunk["movieId"].map(_int_or_none)
        chunk["user_id"] = chunk["userId"].map(_int_or_none)
        chunk["rating_value"] = chunk["rating"].map(_float_or_none)
        chunk["timestamp"] = chunk["timestamp"].map(_int_or_none)

        chunk = chunk.dropna(subset=["movie_lens_id", "user_id", "rating_value", "timestamp"]).copy()
        chunk["tmdb_id"] = chunk["movie_lens_id"].map(valid_lookup)
        chunk = chunk[chunk["tmdb_id"].notna()].copy()
        chunk["tmdb_id"] = chunk["tmdb_id"].map(int)
        chunk = chunk[chunk["tmdb_id"].map(lambda tmdb_id: tmdb_id in movie_ids)].copy()

        for row_number, row in chunk.iterrows():
            movie_lens_id = row["movie_lens_id"]
            user_id = row["user_id"]
            rating = row["rating_value"]
            timestamp = row["timestamp"]
            event_id = f"{user_id}:{movie_lens_id}:{timestamp}:{row_number}"
            if event_id in existing_rating_ids:
                chunk_skipped += 1
                skipped += 1
                continue
            document = {
                "_id": event_id,
                "user_id": user_id,
                "movie_lens_id": movie_lens_id,
                "rating": rating,
                "rated_at": datetime.fromtimestamp(timestamp, tz=timezone.utc),
                "timestamp": timestamp,
            }
            pending_operations.append(ReplaceOne({"_id": event_id}, document, upsert=True))
            existing_rating_ids.add(event_id)
            chunk_processed += 1

        processed += chunk_rows

        if len(pending_operations) >= write_chunk_size:
            database.ratings.bulk_write(pending_operations, ordered=False)
            print(
                f"[CHUNK {chunk_index}] wrote {len(pending_operations)} rating operations; "
                f"processed rows {processed}/{total_rows}; skipped {skipped}; "
                f"elapsed {time.perf_counter() - start_time:.1f}s"
            )
            pending_operations.clear()

        print(
            f"[CHUNK {chunk_index}] rows={chunk_rows} kept={chunk_processed} "
            f"skipped={chunk_skipped} cumulative_skipped={skipped} "
            f"elapsed {time.perf_counter() - start_time:.1f}s"
        )

    if pending_operations:
        database.ratings.bulk_write(pending_operations, ordered=False)
        print(f"[INFO] Final bulk write of {len(pending_operations)} rating operations.")
        pending_operations.clear()

    print(f"[INFO] Rating preparation complete. Processed {processed} rows; skipped {skipped} rows.")
    return processed, skipped


def import_outputs(output_dir):
    tables = _load_tables(output_dir)
    connector = DbConnector()
    database = connector.db
    try:
        _stage("Creating MongoDB collections and indexes", lambda: _create_schema(database))

        credits = _related_indexes(tables["credits"], "id")
        keywords = _related_indexes(tables["keywords"], "id")
        valid_links = _valid_links(tables["links"])
        links = {
            int(row["tmdb_id"]): row
            for _, row in valid_links.iterrows()
        }
        aggregates = _rating_aggregates(tables["ratings"], tables["links"])

        existing_movie_ids = set(database.movies.distinct("_id"))

        def build_movies():
            documents = []
            skipped_existing = 0
            movie_ids_in_this_run = set(existing_movie_ids)
            for _, row in tables["movies"].iterrows():
                document = _movie_document(row, credits, keywords, links, aggregates)
                if document is None:
                    continue
                if document["_id"] in movie_ids_in_this_run:
                    skipped_existing += 1
                    continue
                documents.append(document)
                movie_ids_in_this_run.add(document["_id"])
            print(f"[INFO] Skipped {skipped_existing} movie documents already present in MongoDB.")
            return documents, movie_ids_in_this_run

        movies, movie_ids_for_rating_filter = _stage("Preparing movie documents", build_movies)
        movie_operations = [
            ReplaceOne({"_id": document["_id"]}, document, upsert=True)
            for document in movies
        ]
        if movie_operations:
            _stage(
                f"Upserting {len(movie_operations)} movie documents",
                lambda: database.movies.bulk_write(movie_operations, ordered=False),
            )
        else:
            print("[INFO] No movie documents to insert; all movies already exist in MongoDB.")

        print("[INFO] Starting MovieLens rating document preparation in chunks.")
        _stage(
            "Preparing MovieLens rating documents",
            lambda: _rating_operations(
                database,
                tables["ratings"],
                tables["links"],
                movie_ids_for_rating_filter,
                chunk_size=100_000,
                write_chunk_size=5_000,
            ),
        )
        print(f"[INFO] Database: {database.name}")
        print(f"[INFO] Movies collection: {database.movies.count_documents({})} documents")
        print(f"[INFO] Ratings collection: {database.ratings.count_documents({})} documents")
    finally:
        connector.close_connection()
        print("[DONE] MongoDB connection closed")


def main():
    parser = argparse.ArgumentParser(
        description="Create MongoDB collections and import EDA step 3/7 outputs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("EDA_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)),
        help="Directory containing step_3_*.csv and step_7_movies_metadata.csv.",
    )
    args = parser.parse_args()
    _stage(
        "Importing EDA outputs into MongoDB",
        lambda: import_outputs(args.output_dir),
    )


if __name__ == "__main__":
    main()

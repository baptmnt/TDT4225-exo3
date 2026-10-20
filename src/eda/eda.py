import argparse
import ast
import csv
import json
import time
import warnings
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from tabulate import tabulate


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
DATA_FILES = (
    "movies_metadata.csv",
    "credits_small.csv",
    "keywords.csv",
    "links_small.csv",
    "ratings_small.csv",
)
OUTPUT_DIR = PROJECT_DIR / "outputs" / "eda"

TEXT_COLUMNS = {
    "belongs_to_collection",
    "cast",
    "crew",
    "genres",
    "homepage",
    "imdb_id",
    "keywords",
    "original_language",
    "original_title",
    "overview",
    "poster_path",
    "production_companies",
    "production_countries",
    "spoken_languages",
    "status",
    "tagline",
    "title",
}
BOOLEAN_COLUMNS = {"adult", "video"}
DATE_COLUMNS = {"release_date"}
INTEGER_COLUMNS = {"id", "movieId", "imdbId", "tmdbId", "userId", "timestamp"}
NUMERIC_COLUMNS = {"budget", "popularity", "revenue", "runtime", "vote_average", "vote_count", "rating"}


def _read_csv(path):
    """Read a CSV and repair records split by an unescaped quote."""
    if path.name != "movies_metadata.csv":
        return pd.read_csv(
            path,
            dtype="string",
            keep_default_na=False,
            na_filter=False,
            quotechar='"',
            doublequote=True,
            quoting=csv.QUOTE_MINIMAL,
            on_bad_lines="error",
        )

    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        columns = next(reader)
        repaired_records = []
        for record_index, record in enumerate(reader, start=2):
            if len(record) == len(columns):
                repaired_records.append(record)
                continue

            following_record = next(reader, None)
            if following_record is None:
                raise ValueError(
                    f"Unrepairable record at line {record_index} in {path}"
                )
            if len(record) + len(following_record) - 1 != len(columns):
                raise ValueError(
                    f"Unexpected field count at line {record_index} in {path}"
                )
            repaired_records.append(
                record[:-1]
                + [record[-1] + following_record[0]]
                + following_record[1:]
            )

    return pd.DataFrame(repaired_records, columns=columns, dtype="string")


def load_data(data_dir=DATA_DIR):
    """
    Load the configured CSV files from the data directory.
    """
    data_dir = Path(data_dir)
    missing_files = [name for name in DATA_FILES if not (data_dir / name).is_file()]
    if missing_files:
        raise FileNotFoundError(
            f"Missing CSV file(s) in {data_dir}: {', '.join(missing_files)}"
        )
    return {
        name: _read_csv(data_dir / name)
        for name in DATA_FILES
    }


def _find_table(data, required_columns):
    """Find the single loaded table containing the requested columns."""
    matches = [
        frame
        for frame in data.values()
        if set(required_columns).issubset(frame.columns)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one table with columns {sorted(required_columns)}, "
            f"found {len(matches)}"
        )
    return matches[0]


def _key_series(frame, column):
    """Normalize integer-like key values without dropping leading zeros."""
    values = pd.to_numeric(frame[column], errors="coerce")
    return values.astype("Int64").astype("string")


def _validate_nested_column(frame, filename, column, field_predicates):
    """Parse one nested column once and validate its item fields."""
    malformed = 0
    empty = 0
    item_count = 0
    invalid_fields = {field: 0 for field in field_predicates}
    for value in frame[column]:
        if pd.isna(value) or str(value).strip() == "":
            empty += 1
            continue
        parsed = parse_nested(value)
        if parsed:
            item_count += len(parsed)
            for item in parsed:
                for field, predicate in field_predicates.items():
                    if not isinstance(item, dict) or not predicate(item.get(field)):
                        invalid_fields[field] += 1
        elif str(value).strip() not in {"[]", "{}"}:
            malformed += 1
    rows = [
        {
            "table": filename,
            "column": column,
            "check": "nested_structure",
            "metric": metric,
            "value": value,
        }
        for metric, value in (
            ("empty_values", empty),
            ("malformed_values", malformed),
            ("nested_items", item_count),
        )
    ]
    rows.extend(
        {
            "table": filename,
            "column": column,
            "check": "nested_fields",
            "metric": f"invalid_{field}",
            "value": value,
        }
        for field, value in invalid_fields.items()
    )
    return rows


def validate_related_data(data):
    """Validate table-specific structures, keys, domains, and relationships."""
    rows = []
    movies = data["movies_metadata.csv"]
    movie_ids = _key_series(movies, "id").dropna()
    non_empty = lambda value: value is not None and not pd.isna(value) and bool(
        str(value).strip()
    )

    for filename, columns in (
        ("credits_small.csv", ("cast", "crew")),
        ("keywords.csv", ("keywords",)),
    ):
        frame = data[filename]
        for column in columns:
            predicates = {}
            if column == "cast":
                predicates = {
                    "id": lambda value: pd.notna(pd.to_numeric(value, errors="coerce")),
                    "name": non_empty,
                    "order": lambda value: pd.notna(
                        pd.to_numeric(value, errors="coerce")
                    ),
                }
            elif column == "crew":
                predicates = {
                    "id": lambda value: pd.notna(pd.to_numeric(value, errors="coerce")),
                    "name": non_empty,
                    "job": non_empty,
                }
            else:
                predicates = {
                    "id": lambda value: pd.notna(pd.to_numeric(value, errors="coerce")),
                    "name": non_empty,
                }
            rows.extend(_validate_nested_column(frame, filename, column, predicates))
        ids = _key_series(frame, "id").dropna()
        rows.append({
            "table": filename,
            "column": "id",
            "check": "foreign_key",
            "metric": "orphan_movie_ids",
            "value": int((~ids.isin(set(movie_ids))).sum()),
        })

    links = data["links_small.csv"]
    for column in ("movieId", "imdbId", "tmdbId"):
        values = _key_series(links, column).dropna()
        rows.extend(
            [
                {
                    "table": "links_small.csv",
                    "column": column,
                    "check": "key_quality",
                    "metric": "duplicate_values",
                    "value": int(values.duplicated().sum()),
                },
                {
                    "table": "links_small.csv",
                    "column": column,
                    "check": "key_quality",
                    "metric": "missing_values",
                    "value": int(_missing_mask(links[column]).sum()),
                },
            ]
        )
    tmdb_ids = _key_series(links, "tmdbId").dropna()
    rows.append({
        "table": "links_small.csv",
        "column": "tmdbId",
        "check": "foreign_key",
        "metric": "orphan_movie_ids",
        "value": int((~tmdb_ids.isin(set(movie_ids))).sum()),
    })

    ratings = data["ratings_small.csv"]
    rating_values = pd.to_numeric(ratings["rating"], errors="coerce")
    timestamps = pd.to_numeric(ratings["timestamp"], errors="coerce")
    rows.extend(
        [
            {
                "table": "ratings_small.csv",
                "column": "rating",
                "check": "domain",
                "metric": "outside_0.5_to_5_range",
                "value": int((~rating_values.between(0.5, 5)).sum()),
            },
            {
                "table": "ratings_small.csv",
                "column": "rating",
                "check": "domain",
                "metric": "not_half_point_increment",
                "value": int(((rating_values * 2) % 1 != 0).sum()),
            },
            {
                "table": "ratings_small.csv",
                "column": "timestamp",
                "check": "domain",
                "metric": "invalid_unix_timestamps",
                "value": int(
                    pd.to_datetime(timestamps, unit="s", errors="coerce").isna().sum()
                ),
            },
            {
                "table": "ratings_small.csv",
                "column": "userId,movieId",
                "check": "key_quality",
                "metric": "duplicate_pairs",
                "value": int(ratings.duplicated(["userId", "movieId"]).sum()),
            },
        ]
    )
    link_movie_ids = _key_series(links, "movieId").dropna()
    rated_movie_ids = _key_series(ratings, "movieId").dropna()
    rows.append({
        "table": "ratings_small.csv",
        "column": "movieId",
        "check": "foreign_key",
        "metric": "movie_ids_not_in_links",
        "value": int((~rated_movie_ids.isin(set(link_movie_ids))).sum()),
    })
    return pd.DataFrame(rows, columns=["table", "column", "check", "metric", "value"])


def _missing_mask(series):
    """Return missing values, including whitespace-only CSV fields."""
    return series.isna() | series.astype("string").str.strip().eq("")


def _value_type(value):
    """Infer a simple type from one non-missing value."""
    text = str(value).strip()
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return "boolean"

    numeric = pd.to_numeric(text, errors="coerce")
    if pd.notna(numeric):
        return "integer" if float(numeric).is_integer() else "numeric"

    date = pd.to_datetime(text, errors="coerce")
    if pd.notna(date):
        return "date"

    return "text"


def _infer_unknown_column_type(values):
    """Infer a type only when every observed value supports that type."""
    value_types = values.map(_value_type)
    if value_types.isin({"integer", "numeric"}).all():
        return "numeric" if "numeric" in set(value_types) else "integer"
    if value_types.eq("boolean").all():
        return "boolean"
    if value_types.eq("date").all():
        return "date"
    return "text"


def _infer_column_type(column, series):
    """Determine a column type from known fields, then use a safe fallback."""
    values = series.loc[~_missing_mask(series)]
    if values.empty:
        return "unknown", pd.Series(False, index=series.index)

    if column in TEXT_COLUMNS:
        expected_type = "text"
    elif column in BOOLEAN_COLUMNS:
        expected_type = "boolean"
    elif column in DATE_COLUMNS:
        expected_type = "date"
    elif column in INTEGER_COLUMNS:
        expected_type = "integer"
    elif column in NUMERIC_COLUMNS:
        expected_type = "numeric"
    else:
        expected_type = _infer_unknown_column_type(values)

    if expected_type == "text":
        invalid_mask = pd.Series(False, index=values.index)
    elif expected_type == "numeric":
        invalid_mask = pd.to_numeric(values, errors="coerce").isna()
    elif expected_type == "integer":
        numeric_values = pd.to_numeric(values, errors="coerce")
        invalid_mask = numeric_values.isna() | numeric_values.mod(1).ne(0)
    elif expected_type == "date":
        invalid_mask = pd.to_datetime(values, errors="coerce").isna()
    else:
        normalized = values.astype("string").str.lower()
        invalid_mask = ~normalized.isin({"true", "false"})
    return expected_type, invalid_mask


def inspect_data(data=None, data_dir=DATA_DIR, output_dir=OUTPUT_DIR):
    """Inspect every CSV and write inspection, invalid-value, and duplicate reports."""
    if data is None:
        data = load_data(data_dir)
    rows = []
    invalid_values = []
    duplicate_rows = []

    for filename, frame in data.items():
        duplicate_mask = frame.duplicated(keep=False)
        duplicate_row_count = int(frame.duplicated().sum())
        for index in frame.index[duplicate_mask]:
            duplicate_rows.append(
                {
                    "file": filename,
                    "row_number": index + 2,
                    "duplicate_row": frame.loc[index].to_json(),
                }
            )

        for column in frame.columns:
            series = frame[column]
            missing_count = int(_missing_mask(series).sum())
            expected_type, invalid_mask = _infer_column_type(column, series)
            invalid_count = int(invalid_mask.sum())
            for index in invalid_mask.index[invalid_mask]:
                invalid_values.append(
                    {
                        "file": filename,
                        "row_number": index + 2,
                        "column": column,
                        "value": series.loc[index],
                        "expected_type": expected_type,
                    }
                )
            rows.append(
                {
                    "file": filename,
                    "column": column,
                    "expected_type": expected_type,
                    "pandas_type": str(series.dtype),
                    "row_count": len(frame),
                    "missing_count": missing_count,
                    "invalid_type_count": invalid_count,
                    "duplicate_row_count": duplicate_row_count,
                }
            )

    report = pd.DataFrame(rows)
    related_report = validate_related_data(data)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "step_2_inspect_data.csv"
    report.to_csv(output_path, index=False)
    pd.DataFrame(
        invalid_values,
        columns=["file", "row_number", "column", "value", "expected_type"],
    ).to_csv(output_dir / "step_2_invalid_data.csv", index=False)
    pd.DataFrame(
        duplicate_rows,
        columns=["file", "row_number", "duplicate_row"],
    ).to_csv(
        output_dir / "step_2_duplicate_rows.csv", index=False
    )
    duplicate_movie_ids(data["movies_metadata.csv"]).to_csv(
        output_dir / "step_2_duplicate_movie_ids.csv",
        index=False,
    )
    related_report.to_csv(output_dir / "step_2_related_data_validation.csv", index=False)
    return report


def duplicate_movie_ids(movies):
    """Return movie IDs that occur more than once."""
    ids = movies["id"].astype("string").str.strip()
    counts = ids.dropna().loc[lambda values: values.ne("")].value_counts()
    duplicated = counts[counts > 1].rename_axis("id").reset_index(name="occurrences")
    duplicated["row_numbers"] = duplicated["id"].map(
        lambda movie_id: ",".join(
            str(index + 2)
            for index in movies.index[ids.eq(movie_id)]
        )
    )
    return duplicated


def _record_correction(corrections, table, column, rule, affected_rows):
    """Append a summary of one missing-value correction."""
    corrections.append(
        {
            "table": table,
            "column": column,
            "rule": rule,
            "affected_rows": int(affected_rows),
        }
    )


def handle_missing_data(data, output_dir=OUTPUT_DIR, output_clean_files=False):
    """Apply the step 3 missing-data policy and keep cleaned tables in memory."""
    cleaned = {}
    corrections = []

    for filename, frame in data.items():
        result = frame.copy()
        for column in result.columns:
            blank_mask = result[column].astype("string").str.strip().eq("")
            if blank_mask.any():
                result.loc[blank_mask, column] = pd.NA
                _record_correction(
                    corrections,
                    filename,
                    column,
                    "blank strings converted to missing values",
                    blank_mask.sum(),
                )

        if filename == "movies_metadata.csv":
            normalized_ids = result["id"].astype("string").str.strip()
            row_lengths = result.fillna("").astype("string").apply(
                lambda column: column.str.len()
            ).sum(axis=1)
            rows_to_remove = []
            for _, group in result.loc[
                result["id"].notna() & normalized_ids.ne("")
            ].groupby(normalized_ids):
                if len(group) > 1:
                    rows_to_remove.extend(
                        group.index[row_lengths.loc[group.index].rank(method="first", ascending=False) > 1]
                    )
            duplicate_id_mask = result.index.isin(rows_to_remove)
            if duplicate_id_mask.any():
                result = result.loc[~duplicate_id_mask].copy()
                _record_correction(
                    corrections,
                    filename,
                    "id",
                    "duplicate movie IDs removed; longest row retained",
                    duplicate_id_mask.sum(),
                )

            for column in ("budget", "revenue", "runtime", "vote_count", "vote_average"):
                values = pd.to_numeric(result[column], errors="coerce")
                zero_mask = values.eq(0)
                if zero_mask.any():
                    result.loc[zero_mask, column] = pd.NA
                    _record_correction(
                        corrections,
                        filename,
                        column,
                        "zero sentinel converted to missing value",
                        zero_mask.sum(),
                    )

            missing_status = result["status"].isna()
            if missing_status.any():
                result.loc[missing_status, "status"] = "Unknown"
                _record_correction(
                    corrections,
                    filename,
                    "status",
                    "missing status replaced with Unknown",
                    missing_status.sum(),
                )

        if "tmdbId" in result.columns:
            missing_tmdb_id = result["tmdbId"].isna()
            if missing_tmdb_id.any():
                result = result.loc[~missing_tmdb_id].copy()
                _record_correction(
                    corrections,
                    filename,
                    "tmdbId",
                    "rows without tmdbId removed",
                    missing_tmdb_id.sum(),
                )

        cleaned[filename] = result

    if output_clean_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename, frame in cleaned.items():
            frame.to_csv(output_dir / f"step_3_{filename}", index=False)
        pd.DataFrame(
            corrections,
            columns=["table", "column", "rule", "affected_rows"],
        ).to_csv(output_dir / "step_3_missing_data.csv", index=False)
    return cleaned


def prepare_movies_for_analysis(movies):
    """Coerce movie fields to analysis-ready types without changing the input."""
    result = movies.copy()
    numeric_columns = (
        "budget",
        "id",
        "popularity",
        "revenue",
        "runtime",
        "vote_average",
        "vote_count",
    )
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["release_date"] = pd.to_datetime(result["release_date"], errors="coerce")
    return result


def transform_movies(movies, output_dir=OUTPUT_DIR, output_clean_files=False):
    """Add date dimensions required by later EDA analyses."""
    result = prepare_movies_for_analysis(movies)
    result["release_year"] = result["release_date"].dt.year.astype("Int64")
    result["release_month"] = result["release_date"].dt.month.astype("Int64")
    decade = (result["release_year"] // 10) * 10
    result["release_decade"] = decade.astype("string") + "s"

    if output_clean_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_dir / "step_5_movies_metadata.csv", index=False)
    return result


def run_step_5(data, output_dir=OUTPUT_DIR, output_clean_files=False):
    """Run data transformation and return all tables for subsequent steps."""
    transformed = {**data}
    transformed["movies_metadata.csv"] = transform_movies(
        data["movies_metadata.csv"],
        output_dir=output_dir,
        output_clean_files=output_clean_files,
    )
    return transformed


def parse_nested(value):
    """Parse a serialized list of dictionaries from the movie metadata."""
    if pd.isna(value) or value in ("", "[]", "{}"):
        return []
    try:
        parsed = ast.literal_eval(str(value))
    except (SyntaxError, ValueError):
        try:
            parsed = json.loads(str(value))
        except (json.JSONDecodeError, TypeError):
            return []
    return parsed if isinstance(parsed, list) else []


def explode_names(frame, column):
    """Return one row per nested movie item with its movie identifier."""
    rows = []
    for movie_id, values in frame[["id", column]].itertuples(index=False):
        for item in parse_nested(values):
            if isinstance(item, dict) and item.get("name"):
                rows.append({"id": movie_id, "name": item["name"]})
    return pd.DataFrame(rows, columns=["id", "name"])


def plot_movie_distributions(
    movies,
    output_dir=OUTPUT_DIR,
    output_eda_files=False,
):
    """Create step 4 movie distributions and return descriptive statistics."""
    numeric_columns = [
        "budget",
        "revenue",
        "popularity",
        "runtime",
        "vote_average",
        "vote_count",
    ]
    statistics = movies[numeric_columns].describe().transpose()

    if output_eda_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        statistics.to_csv(output_dir / "step_4_movie_descriptive_statistics.csv")
        figure, axes = plt.subplots(2, 3, figsize=(16, 9))
        for axis, column in zip(axes.flat, numeric_columns):
            values = movies[column].dropna()
            if column in {"budget", "revenue", "popularity", "vote_count"}:
                values = values[values >= 0]
                values = np.log1p(values)
                axis.set_xlabel("log(1 + value)")
            else:
                axis.set_xlabel(column.replace("_", " ").title())
            sns.histplot(values, bins=40, ax=axis)
            axis.set_title(column.replace("_", " ").title())
            axis.set_ylabel("Number of movies")
        figure.suptitle("Movie numeric distributions", y=1.02)
        figure.tight_layout()
        figure.savefig(output_dir / "step_4_01_movie_distributions.png", dpi=160)
        plt.close(figure)

    return statistics


def count_movie_statuses(movies, output_dir=OUTPUT_DIR, output_eda_files=False):
    """Count movies by status and return the resulting table."""
    status_counts = (
        movies["status"]
        .value_counts(dropna=False)
        .rename_axis("status")
        .reset_index(name="movie_count")
    )
    if output_eda_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        status_counts.to_csv(output_dir / "step_4_status_counts.csv", index=False)
    return status_counts


def plot_release_trend(movies, output_dir=OUTPUT_DIR, output_eda_files=False):
    """Create the release trend and return yearly movie counts."""
    yearly_movies = movies.copy()
    yearly_movies["release_year"] = yearly_movies["release_date"].dt.year.astype("Int64")
    yearly = (
        yearly_movies.dropna(subset=["release_year"])
        .query("release_year >= 1900 and release_year <= 2020")
        .groupby("release_year")
        .size()
        .reset_index(name="movie_count")
    )
    if output_eda_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        yearly.to_csv(output_dir / "step_4_release_counts_by_year.csv", index=False)
        figure, axis = plt.subplots(figsize=(12, 5))
        sns.lineplot(data=yearly, x="release_year", y="movie_count", ax=axis)
        axis.set_title("Movies released by year")
        axis.set_xlabel("Release year")
        axis.set_ylabel("Number of movies")
        figure.tight_layout()
        figure.savefig(output_dir / "step_4_02_release_trend.png", dpi=160)
        plt.close(figure)
    return yearly


def plot_ratings(ratings, output_dir=OUTPUT_DIR, output_eda_files=False):
    """Create rating distributions and return monthly and total counts."""
    result = ratings.copy()
    result["rating"] = pd.to_numeric(result["rating"], errors="coerce")
    result["timestamp"] = pd.to_numeric(result["timestamp"], errors="coerce")
    result["rating_date"] = pd.to_datetime(result["timestamp"], unit="s", errors="coerce")
    rating_counts = (
        result.dropna(subset=["rating"])
        .groupby("rating")
        .size()
        .reset_index(name="rating_count")
        .sort_values("rating")
    )
    monthly_counts = (
        result.dropna(subset=["rating_date"])
        .set_index("rating_date")
        .resample("ME")
        .size()
        .rename("rating_count")
        .reset_index()
    )
    if output_eda_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        rating_counts.to_csv(output_dir / "step_4_rating_counts.csv", index=False)
        figure, axes = plt.subplots(1, 2, figsize=(14, 5))
        sns.countplot(
            data=result,
            x="rating",
            order=rating_counts["rating"].tolist(),
            ax=axes[0],
            color="#4c72b0",
        )
        axes[0].set_title("Rating distribution")
        monthly_counts.plot(x="rating_date", y="rating_count", ax=axes[1], legend=False)
        axes[1].set_title("Ratings submitted over time")
        axes[1].set_xlabel("Date")
        axes[1].set_ylabel("Ratings")
        figure.tight_layout()
        figure.savefig(output_dir / "step_4_04_ratings.png", dpi=160)
        plt.close(figure)
    return {"rating_counts": rating_counts, "monthly_counts": monthly_counts}


def plot_nested_features(movies, output_dir=OUTPUT_DIR, output_eda_files=False):
    """Create nested-feature counts and return all derived tables."""
    feature_columns = {
        "genres": "step_4_genre_counts.csv",
        "spoken_languages": "step_4_language_counts.csv",
        "production_countries": "step_4_country_counts.csv",
    }
    counts_by_file = {}
    for column, filename in feature_columns.items():
        values = explode_names(movies, column)
        counts_by_file[filename] = (
            values["name"].value_counts()
            .head(20)
            .rename_axis("name")
            .reset_index(name="movie_count")
        )

    genres = explode_names(movies, "genres")
    genre_summary = (
        genres.merge(movies[["id", "vote_average", "vote_count"]], on="id")
        .groupby("name")
        .agg(
            movie_count=("id", "nunique"),
            mean_vote=("vote_average", "mean"),
            median_vote=("vote_average", "median"),
            total_votes=("vote_count", "sum"),
        )
        .query("movie_count >= 20")
        .sort_values("movie_count", ascending=False)
        .reset_index()
    )
    if output_eda_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename, counts in counts_by_file.items():
            counts.to_csv(output_dir / filename, index=False)
        genre_summary.to_csv(output_dir / "step_4_genre_rating_summary.csv", index=False)
        figure, axes = plt.subplots(1, 3, figsize=(20, 8))
        for axis, (filename, counts) in zip(axes, counts_by_file.items()):
            sns.barplot(data=counts, x="movie_count", y="name", ax=axis, color="#55a868")
            axis.set_title(filename.replace("_counts.csv", "").title())
        figure.tight_layout()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Glyph .* missing from font")
            figure.savefig(output_dir / "step_4_05_nested_features.png", dpi=160)
        plt.close(figure)
    return {**counts_by_file, "genre_rating_summary": genre_summary}


def plot_relationships(movies, output_dir=OUTPUT_DIR, output_eda_files=False):
    """Create correlation and budget/revenue plots for step 6."""
    columns = [
        "budget",
        "revenue",
        "popularity",
        "runtime",
        "vote_average",
        "vote_count",
    ]
    correlation = movies[columns].corr(method="spearman")
    sample = movies.dropna(subset=["budget", "revenue"]).query("budget > 0 and revenue > 0")
    if output_eda_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        correlation.reset_index().rename(columns={"index": "variable"}).to_csv(
            output_dir / "step_6_spearman_correlation.csv", index=False
        )
        figure, axis = plt.subplots(figsize=(9, 7))
        sns.heatmap(correlation, annot=True, fmt=".2f", cmap="vlag", center=0, ax=axis)
        axis.set_title("Spearman correlations of movie measures")
        figure.tight_layout()
        figure.savefig(output_dir / "step_6_01_correlations.png", dpi=160)
        plt.close(figure)
        figure, axis = plt.subplots(figsize=(9, 6))
        sns.scatterplot(
            data=sample,
            x="budget",
            y="revenue",
            hue="vote_average",
            size="vote_count",
            sizes=(10, 180),
            alpha=0.45,
            legend=False,
            ax=axis,
        )
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_title("Budget versus revenue for movies with both values")
        figure.tight_layout()
        figure.savefig(output_dir / "step_6_02_budget_revenue.png", dpi=160)
        plt.close(figure)
    return {"correlation": correlation, "budget_revenue": sample}


def plot_runtime_by_decade_genre(
    movies, output_dir=OUTPUT_DIR, output_eda_files=False
):
    """Summarize and visualize runtime by release decade and primary genre."""
    result = movies.copy()
    result["primary_genre"] = result["genres"].map(
        lambda value: next(
            (
                item["name"]
                for item in parse_nested(value)
                if isinstance(item, dict) and item.get("name")
            ),
            pd.NA,
        )
    )
    summary = (
        result.dropna(subset=["release_decade", "primary_genre", "runtime"])
        .groupby(["release_decade", "primary_genre"], as_index=False)
        .agg(
            median_runtime=("runtime", "median"),
            movie_count=("id", "nunique"),
        )
        .sort_values(["release_decade", "median_runtime"], ascending=[True, False])
    )
    if output_eda_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary.to_csv(output_dir / "step_6_runtime_by_decade_genre.csv", index=False)
        heatmap = summary.pivot(
            index="release_decade",
            columns="primary_genre",
            values="median_runtime",
        ).astype(float)
        figure, axis = plt.subplots(figsize=(16, 9))
        sns.heatmap(heatmap, cmap="YlGnBu", annot=True, fmt=".0f", ax=axis)
        axis.set_title("Median runtime by decade and primary genre")
        axis.set_xlabel("Primary genre")
        axis.set_ylabel("Release decade")
        figure.tight_layout()
        figure.savefig(output_dir / "step_6_03_runtime_by_decade_genre.png", dpi=160)
        plt.close(figure)
    return summary


def plot_vote_relationships(movies, output_dir=OUTPUT_DIR, output_eda_files=False):
    """Visualize relationships between popularity, votes, and average rating."""
    result = movies[
        ["popularity", "vote_count", "vote_average"]
    ].dropna().query("popularity >= 0 and vote_count > 0")
    if output_eda_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        figure, axes = plt.subplots(1, 2, figsize=(16, 6))
        sns.scatterplot(
            data=result, x="vote_count", y="popularity", alpha=0.35, ax=axes[0]
        )
        axes[0].set_xscale("log")
        axes[0].set_yscale("log")
        axes[0].set_title("Popularity versus vote count")
        axes[0].set_xlabel("Vote count (log scale)")
        axes[0].set_ylabel("Popularity (log scale)")
        sns.scatterplot(
            data=result, x="vote_count", y="vote_average", alpha=0.35, ax=axes[1]
        )
        axes[1].set_xscale("log")
        axes[1].set_title("Average rating versus vote count")
        axes[1].set_xlabel("Vote count (log scale)")
        axes[1].set_ylabel("Average rating")
        figure.tight_layout()
        figure.savefig(output_dir / "step_6_04_vote_relationships.png", dpi=160)
        plt.close(figure)
    return result


def run_step_6(data, output_dir=OUTPUT_DIR, output_eda_files=False):
    """Run relationship analyses on the transformed step 5 data."""
    movies = data["movies_metadata.csv"]
    return {
        "relationships": plot_relationships(
            movies, output_dir=output_dir, output_eda_files=output_eda_files
        ),
        "runtime_by_decade_genre": plot_runtime_by_decade_genre(
            movies, output_dir=output_dir, output_eda_files=output_eda_files
        ),
        "vote_relationships": plot_vote_relationships(
            movies, output_dir=output_dir, output_eda_files=output_eda_files
        ),
    }


def run_step_7(data, output_dir=OUTPUT_DIR, output_clean_files=False):
    """Remove movies released strictly after July 2017."""
    cutoff = pd.Timestamp("2017-07-31")
    movies = data["movies_metadata.csv"].copy()
    release_dates = pd.to_datetime(movies["release_date"], errors="coerce")
    keep = release_dates.isna() | release_dates.le(cutoff)
    filtered = {**data, "movies_metadata.csv": movies.loc[keep].copy()}

    if output_clean_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filtered["movies_metadata.csv"].to_csv(
            output_dir / "step_7_movies_metadata.csv",
            index=False,
        )
    return filtered


def _run_stage(name, function):
    """Run one pipeline stage and print its elapsed time."""
    started_at = time.perf_counter()
    print(f"[START] {name}")
    result = function()
    elapsed = time.perf_counter() - started_at
    print(f"[DONE] {name} ({elapsed:.2f}s)")
    return result


def run_step_4(
    data,
    output_dir=OUTPUT_DIR,
    output_eda_files=False,
):
    """Run EDA analysis on the step 3 data held in memory."""
    movies = prepare_movies_for_analysis(data["movies_metadata.csv"])
    results = {"movie_statistics": plot_movie_distributions(
        movies,
        output_dir=output_dir,
        output_eda_files=output_eda_files,
    )}
    results["status_counts"] = count_movie_statuses(
        movies,
        output_dir=output_dir,
        output_eda_files=output_eda_files,
    )
    results["release_counts"] = plot_release_trend(
        movies, output_dir=output_dir, output_eda_files=output_eda_files
    )
    results["ratings"] = plot_ratings(
        _find_table(data, ("rating", "timestamp")),
        output_dir=output_dir,
        output_eda_files=output_eda_files,
    )
    results["nested_features"] = plot_nested_features(
        movies, output_dir=output_dir, output_eda_files=output_eda_files
    )
    return movies, results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect and clean EDA input data.")
    parser.add_argument(
        "--output-clean-files",
        action="store_true",
        help="Write cleaned step 3 CSV files to disk.",
    )
    parser.add_argument(
        "--output-eda-files",
        action="store_true",
        help="Write step 4 EDA outputs to disk.",
    )
    args = parser.parse_args()
    start_time = time.perf_counter()
    data = _run_stage("Loading input tables", load_data)
    report = _run_stage("Step 2 - inspecting data", lambda: inspect_data(data=data))
    print(f"Inspection written to {OUTPUT_DIR / 'step_2_inspect_data.csv'}")
    duplicated_ids = duplicate_movie_ids(data["movies_metadata.csv"])
    print(
        "Duplicate movie IDs: "
        f"{len(duplicated_ids)} IDs ({duplicated_ids['occurrences'].sum()} rows)"
    )
    cleaned = _run_stage(
        "Step 3 - handling missing data",
        lambda: handle_missing_data(
            data,
            output_clean_files=args.output_clean_files,
        ),
    )
    if args.output_clean_files:
        print(f"Cleaned CSV files written to {OUTPUT_DIR}")
    movies, statistics = _run_stage(
        "Step 4 - running descriptive EDA",
        lambda: run_step_4(
            cleaned,
            output_eda_files=args.output_eda_files,
        ),
    )
    step_4_data = {**cleaned, "movies_metadata.csv": movies}
    transformed = _run_stage(
        "Step 5 - transforming data",
        lambda: run_step_5(
            step_4_data,
            output_clean_files=args.output_clean_files,
        ),
    )
    _run_stage(
        "Step 6 - visualizing relationships",
        lambda: run_step_6(
            transformed,
            output_eda_files=args.output_eda_files,
        ),
    )
    filtered = _run_stage(
        "Step 7 - filtering release dates",
        lambda: run_step_7(
            transformed,
            output_clean_files=args.output_clean_files,
        ),
    )
    if args.output_eda_files:
        print(f"EDA outputs written to {OUTPUT_DIR}")
    print(f"Step 4 analyzed {len(movies)} movies")
    print(f"Step 7 retained {len(filtered['movies_metadata.csv'])} movies")
    print(f"[DONE] Full pipeline ({time.perf_counter() - start_time:.2f}s)")

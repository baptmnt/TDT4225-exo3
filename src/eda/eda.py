import argparse
import ast
import csv
import json
import time
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
    "credits.csv",
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

    value_types = values.map(_value_type)
    if expected_type == "text":
        invalid_mask = pd.Series(False, index=values.index)
    elif expected_type == "numeric":
        invalid_mask = ~value_types.isin({"integer", "numeric"})
    else:
        invalid_mask = value_types.ne(expected_type)
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
    return report


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
    result["timestamp"] = pd.to_numeric(result["timestamp"], errors="coerce")
    result["rating_date"] = pd.to_datetime(result["timestamp"], unit="s", errors="coerce")
    rating_counts = result.groupby("rating").size().reset_index(name="rating_count")
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
        sns.countplot(data=result, x="rating", ax=axes[0], color="#4c72b0")
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
        figure.savefig(output_dir / "step_4_05_nested_features.png", dpi=160)
        plt.close(figure)
    return {**counts_by_file, "genre_rating_summary": genre_summary}


def plot_relationships(movies, output_dir=OUTPUT_DIR, output_eda_files=False):
    """Create correlation and budget/revenue plots and return derived tables."""
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
            output_dir / "step_4_spearman_correlation.csv", index=False
        )
        figure, axis = plt.subplots(figsize=(9, 7))
        sns.heatmap(correlation, annot=True, fmt=".2f", cmap="vlag", center=0, ax=axis)
        axis.set_title("Spearman correlations of movie measures")
        figure.tight_layout()
        figure.savefig(output_dir / "step_4_06_correlations.png", dpi=160)
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
        figure.savefig(output_dir / "step_4_07_budget_revenue.png", dpi=160)
        plt.close(figure)
    return {"correlation": correlation, "budget_revenue": sample}


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
    results["release_counts"] = plot_release_trend(
        movies, output_dir=output_dir, output_eda_files=output_eda_files
    )
    results["ratings"] = plot_ratings(
        data["ratings_small.csv"],
        output_dir=output_dir,
        output_eda_files=output_eda_files,
    )
    results["nested_features"] = plot_nested_features(
        movies, output_dir=output_dir, output_eda_files=output_eda_files
    )
    results["relationships"] = plot_relationships(
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
    data = load_data()
    report = inspect_data(data=data)
    print(f"Inspection written to {OUTPUT_DIR / 'step_2_inspect_data.csv'}")
    #print(tabulate(report, headers="keys", tablefmt="fancy_grid", showindex=False))
    cleaned = handle_missing_data(
        data,
        output_clean_files=args.output_clean_files,
    )
    if args.output_clean_files:
        print(f"Cleaned CSV files written to {OUTPUT_DIR}")
    movies, statistics = run_step_4(
        cleaned,
        output_eda_files=args.output_eda_files,
    )
    step_4_data = {**cleaned, "movies_metadata.csv": movies}
    transformed = run_step_5(
        step_4_data,
        output_clean_files=args.output_clean_files,
    )
    if args.output_eda_files:
        print(f"EDA outputs written to {OUTPUT_DIR}")
    print(f"Step 4 analyzed {len(movies)} movies")
    elapsed_time = time.perf_counter() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")

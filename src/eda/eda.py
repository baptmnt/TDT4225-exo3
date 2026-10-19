import argparse
import csv
import time
from pathlib import Path

import pandas as pd
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


def inspect_data(data_dir=DATA_DIR, output_dir=OUTPUT_DIR):
    """Inspect every CSV and write inspection, invalid-value, and duplicate reports."""
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


def handle_missing_data(data, output_dir=OUTPUT_DIR, output_files=False):
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

    if output_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename, frame in cleaned.items():
            frame.to_csv(output_dir / f"step_3_cleaned_{filename}", index=False)
        pd.DataFrame(
            corrections,
            columns=["table", "column", "rule", "affected_rows"],
        ).to_csv(output_dir / "step_3_missing_data.csv", index=False)
    return cleaned


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect and clean EDA input data.")
    parser.add_argument(
        "--output-files",
        action="store_true",
        help="Write cleaned tables and the step 3 correction report to disk.",
    )
    args = parser.parse_args()
    start_time = time.perf_counter()
    report = inspect_data()
    print(f"Inspection written to {OUTPUT_DIR / 'step_2_inspect_data.csv'}")
    print(tabulate(report, headers="keys", tablefmt="fancy_grid", showindex=False))
    handle_missing_data(load_data(), output_files=args.output_files)
    if args.output_files:
        print(f"Cleaned data written to {OUTPUT_DIR}")
    elapsed_time = time.perf_counter() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")

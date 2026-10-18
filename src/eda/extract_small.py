"""Extract the first N data rows from a CSV into a *_small.csv file."""

import argparse
import csv
from pathlib import Path


def small_output_path(input_path: Path) -> Path:
    """Return the output path obtained by inserting ``_small`` before .csv."""
    return input_path.with_name(f"{input_path.stem}_small{input_path.suffix}")


def extract_rows(input_path: Path, row_count: int, output_path: Path | None = None) -> Path:
    """Copy the header and the first ``row_count`` rows to a small CSV file."""
    if row_count < 0:
        raise ValueError("row_count must be greater than or equal to zero")
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    if input_path.suffix.lower() != ".csv":
        raise ValueError("The input file must have a .csv extension")

    output_path = output_path or small_output_path(input_path)
    if output_path.resolve() == input_path.resolve():
        raise ValueError("The output file must be different from the input file")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with (
        input_path.open("r", encoding="utf-8", newline="") as source,
        output_path.open("w", encoding="utf-8", newline="") as destination,
    ):
        reader = csv.reader(source)
        writer = csv.writer(destination)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError(f"Input CSV is empty: {input_path}") from error

        writer.writerow(header)
        for index, row in enumerate(reader):
            if index >= row_count:
                break
            writer.writerow(row)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract the first X data rows into a *_small.csv file."
    )
    parser.add_argument("input_file", type=Path, help="CSV file to read")
    parser.add_argument("row_count", type=int, help="Number of data rows to extract")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path; defaults to <input>_small.csv",
    )
    args = parser.parse_args()

    output_path = extract_rows(args.input_file, args.row_count, args.output)
    print(f"Created {output_path}")


if __name__ == "__main__":
    main()

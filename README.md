# TDT4225 – Movie Data Pipeline

*AI-generated README*

This repository contains the work for a TDT4225 assignment on processing and
querying movie data with Python, pandas, and MongoDB.

The project has three main parts:

1. **Exploratory data analysis (EDA)** of the MovieLens/TMDb CSV files.
2. **Data preparation and import** into MongoDB collections.
3. **MongoDB aggregation queries** for the assignment questions.

## Repository status and input data

The raw CSV files are intentionally ignored by Git. Before running the
pipeline, provide the following files in `data/`:

- `movies_metadata.csv`
- `credits.csv`
- `keywords.csv`
- `links.csv`
- `ratings.csv`

The repository does contain committed EDA result files in `outputs/eda/`.
Those files are reference artifacts from a previous run; they are not a
replacement for the input data required by the scripts.

## Requirements

- Python 3.10 or newer
- A reachable MongoDB server
- The packages listed in [`requirements.txt`](requirements.txt)

Create and activate a virtual environment, then install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## MongoDB configuration

[`src/DbConnector.py`](src/DbConnector.py) reads the connection settings from
a `.env` file in the repository root. Create that file locally; it is ignored
by Git:

```dotenv
DATABASE=your_database
HOST=your_mongodb_host
USER=your_mongodb_user
PASSWORD=your_mongodb_password
```

The connector URL-encodes the connection values before creating a
`pymongo.MongoClient`. Do not commit credentials or other secrets.

## Running the pipeline

Run the EDA and cleaning pipeline from the repository root:

```bash
python src/eda/eda.py
```

The script performs the following stages:

1. Loads and parses the five CSV tables.
2. Inspects column types, missing values, malformed values, nested fields,
   duplicate movie IDs, and relationships between related tables.
3. Handles missing data and records the corrections it makes.
4. Computes descriptive statistics and distributions for movies, releases,
   budgets, ratings, genres, languages, countries, and statuses.
5. Transforms movie data, including parsing nested JSON-like columns and
   exploding nested names where needed.
6. Visualizes correlations and relationships such as budget/revenue,
   popularity by decade and genre, and vote relationships.
7. Filters movies to rows with usable release dates and prepares the movie
   table used by the import step.

By default, the script writes the inspection report to
`outputs/eda/step_2_inspect_data.csv` and keeps most generated files in
memory. Use the flags below to persist the corresponding outputs:

```bash
python src/eda/eda.py \
  --output-clean-files \
  --output-eda-files
```

- `--output-clean-files` writes cleaned step 3 CSV files and
  `step_7_movies_metadata.csv`.
- `--output-eda-files` writes step 4 and step 6 CSV summaries and PNG plots.

The importer expects the output directory to contain exactly one matching file
for each required step 3 table and the step 7 movie table. Import the prepared
data with:

```bash
python src/import_data.py
```

To use a different output directory:

```bash
python src/import_data.py --output-dir /path/to/eda/outputs
```

The importer:

- creates the `movies` and `ratings` collections if necessary;
- creates indexes for TMDb IDs, MovieLens IDs, users, collections, and text
  search over overviews and taglines;
- converts scalar and nested CSV values into MongoDB-friendly types;
- joins movie metadata with credits, keywords, external IDs, and aggregated
  MovieLens ratings;
- bulk-upserts movie and rating documents in chunks; and
- prints the final document counts.

The import is designed to be repeatable: existing documents are replaced or
upserted by their stable identifiers rather than blindly duplicated.

## MongoDB document model

The importer creates two collections:

### `movies`

Movie documents use the TMDb movie ID as `_id` and include metadata such as
title, release information, budget, revenue, runtime, popularity, TMDb vote
statistics, and embedded collections for:

- genres
- production companies and countries
- spoken languages
- keywords
- cast
- crew
- movie collections

MovieLens aggregates are stored as `rating_average` and `rating_count`.

### `ratings`

Rating documents contain the user ID, MovieLens movie ID, rating value, rating
date, and an event identifier. The `movie_lens_id` field joins rating events
to movie documents.

The complete committed field/type reference is available in
[`MONGODB_SCHEMA_KEYS.md`](MONGODB_SCHEMA_KEYS.md).

## Running the query workspace

[`src/task_2.py`](src/task_2.py) provides a `MovieQueryWorkspace` around the
`movies` and `ratings` collections. It contains aggregation-pipeline methods
for questions 1–10, helpers for printing pipelines and tabulated results, and
a `run_all_questions()` method.

The script entry point currently connects to MongoDB and runs question 8:

```bash
python src/task_2.py
```

To run another question or execute all questions, import the class and call
the desired method:

```python
from src.task_2 import MovieQueryWorkspace

workspace = MovieQueryWorkspace()
workspace.q1()
# or:
# workspace.run_all_questions()
```

The query methods return aggregation results where implemented and print them
in a readable grid using `tabulate`. Some methods are assignment
placeholders and are intended to be completed or adapted as needed.

## Utility scripts

- [`src/eda/extract_small.py`](src/eda/extract_small.py) copies the header and
  first *N* data rows of a CSV into a `<name>_small.csv` file:

  ```bash
  python src/eda/extract_small.py data/movies_metadata.csv 1000
  ```

- [`src/example.py`](src/example.py) is a basic MongoDB example that creates a
  temporary collection, inserts sample documents, reads them, and drops the
  collection.

## Directory layout

```text
.
├── data/                 # local raw CSV inputs (ignored by Git)
├── outputs/eda/          # committed EDA reports, summaries, and plots
├── requirements.txt      # Python dependencies
├── MONGODB_SCHEMA_KEYS.md
└── src/
    ├── DbConnector.py    # .env-based MongoDB connection helper
    ├── eda/
    │   ├── eda.py       # validation, cleaning, EDA, and visualizations
    │   └── extract_small.py
    ├── import_data.py    # cleaned CSV -> MongoDB importer
    ├── task_2.py         # MongoDB aggregation query workspace
    └── example.py        # simple MongoDB API example
```

## Notes

- Run commands from the repository root so the scripts resolve `data/` and
  `outputs/eda/` correctly.
- `outputs/eda/step_3_*` and `outputs/eda/step_7_movies_metadata.csv` are
  ignored because they are generated intermediate files.
- The committed [`q1_ai_answer.txt`](q1_ai_answer.txt) contains a standalone
  example aggregation for one of the assignment questions.

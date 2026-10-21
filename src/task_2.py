import json
from typing import Any, List, Optional

from tabulate import tabulate

from src.DbConnector import DbConnector


class MovieQueryWorkspace:
    """Simple MongoDB query shell for movie analysis.

    This version keeps the practical display helpers, but it does not hardcode
    any answer to the questions. The goal is to make it easy to write and
    inspect MongoDB pipelines, without pretending the results are already known.
    """

    def __init__(self, db: Optional[Any] = None):
        self.db = db if db is not None else DbConnector().db

    @property
    def movies(self):
        return self.db["movies"]

    def print_query(self, title: str, pipeline: List[dict]) -> List[dict]:
        """Pretty-print a MongoDB pipeline without executing it."""
        print(f"\n{'=' * 80}")
        print(title)
        print(f"{'=' * 80}\n")
        print("Query:")
        if not pipeline:
            print("TODO: fill this pipeline")
        else:
            print(json.dumps(pipeline, indent=2, default=str))
        return pipeline

    def print_results(self, title: str, rows: List[dict]) -> List[dict]:
        """Pretty-print result rows using tabulate."""
        print(f"\n{'=' * 80}")
        print(title)
        print(f"{'=' * 80}\n")
        if not rows:
            print("No result yet. Run the query when ready.")
            return rows
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def run_query(self, pipeline):
        """Execute a MongoDB pipeline when you are ready."""
        return list(self.movies.aggregate(pipeline))

    def q1_movies_by_release_year(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q1 - Movies by release year", pipeline)

    def q2_top_genres_by_count(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q2 - Top genres by count", pipeline)

    def q3_average_runtime_by_genre(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q3 - Average runtime by genre", pipeline)

    def q4_top_movies_by_revenue(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q4 - Top movies by revenue", pipeline)

    def q5_average_vote_by_decade(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q5 - Average vote by decade", pipeline)

    def q6_top_production_countries(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q6 - Top production countries", pipeline)

    def q7_top_actors_by_appearances(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q7 - Top actors by appearances", pipeline)

    def q8_top_directors_by_movies(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q8 - Top directors by movie count", pipeline)

    def q9_movies_by_status(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q9 - Movies by status", pipeline)

    def q10_movies_by_original_language(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q10 - Movies by original language", pipeline)

    def run_all_questions(self) -> List[Any]:
        """Display all question placeholders in a clean list."""
        return [
            self.q1_movies_by_release_year(),
            self.q2_top_genres_by_count(),
            self.q3_average_runtime_by_genre(),
            self.q4_top_movies_by_revenue(),
            self.q5_average_vote_by_decade(),
            self.q6_top_production_countries(),
            self.q7_top_actors_by_appearances(),
            self.q8_top_directors_by_movies(),
            self.q9_movies_by_status(),
            self.q10_movies_by_original_language(),
        ]


if __name__ == "__main__":
    workspace = MovieQueryWorkspace()
    print("MongoDB query workspace ready.")
    print("Use methods such as workspace.q1_movies_by_release_year()")
    print("or workspace.run_all_questions().")

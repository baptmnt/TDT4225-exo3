import json
import pprint
from typing import Any, List, Optional

from tabulate import tabulate

from DbConnector import DbConnector


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
            pprint.pp(pipeline)
        return pipeline

    def print_results(self, title: str, rows: List[dict]) -> List[dict]:
        """Pretty-print result rows with pprint."""
        print(f"\n{'=' * 80}")
        print(title)
        print(f"{'=' * 80}\n")
        if not rows:
            print("No result yet. Run the query when ready.")
            return rows
        pprint.pp(rows)
        return rows

    def run_query(self, pipeline):
        """Execute a MongoDB pipeline when you are ready."""
        return list(self.movies.aggregate(pipeline))

    def q1(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            {"$match": {"revenue": {"$gt": 0}}},
            {"$project": {
                "revenue": 1,
                "title": 1,
                "vote_average": 1,
                "directors": {
                    "$filter": {
                        "input": "$crew",
                        "as": "c",
                        "cond": {"$eq": ["$$c.job", "Director"]},
                    }
                },
            }},
            {"$unwind": "$directors"},
            {"$group": {
                "_id": "$directors.person_id",
                "director": {"$first": "$directors.name"},
                "movie_count": {"$sum": 1},
                "mean_vote_average": {"$avg": "$vote_average"},
                "median_revenue": {"$median": {"input": "$revenue", "method": "approximate"}},
            }},
            {"$match": {"movie_count": {"$gte": 5}}},
            {"$sort": {"median_revenue": -1}},
            {"$limit": 10},
            {"$project": {
                "_id": 0,
                "director": 1,
                "movie_count": 1,
                "median_revenue": 1,
                "mean_vote_average": {"$round": ["$mean_vote_average", 2]},
            }},
        ]

        rows = self.run_query(pipeline)
        print("\nQ1")
        print("Query:")
        pprint.pp(pipeline)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q2(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q2", pipeline)

    def q3(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q3", pipeline)

    def q4(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q4", pipeline)

    def q5(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q5", pipeline)

    def q6(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q6", pipeline)

    def q7(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q7", pipeline)

    def q8(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q8", pipeline)

    def q9(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q9", pipeline)

    def q10(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = []
        return self.print_query("Q10", pipeline)

    def run_all_questions(self) -> List[Any]:
        """Display all question placeholders in a clean list."""
        return [
            self.q1(),
            self.q2(),
            self.q3(),
            self.q4(),
            self.q5(),
            self.q6(),
            self.q7(),
            self.q8(),
            self.q9(),
            self.q10(),
        ]


if __name__ == "__main__":
    workspace = MovieQueryWorkspace()
    print("MongoDB query workspace ready.")
    workspace.q1()

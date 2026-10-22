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

    @property
    def ratings(self):
        return self.db["ratings"]

    def print_query(self, title: str, pipeline: List[dict]) -> List[dict]:
        """Pretty-print a MongoDB pipeline without executing it."""
        print(f"\n{'=' * 80}")
        print(title)
        print(f"{'=' * 80}\n")
        print("Query:")
        if not pipeline:
            print("TODO: fill this pipeline")
        else:
            pprint.PrettyPrinter(
                indent=2,
                width=120,
                sort_dicts=False,
            ).pprint(pipeline)
        return pipeline

    def print_results(self, title: str, rows: List[dict]) -> List[dict]:
        """Pretty-print result rows with tabulate."""
        print(f"\n{'=' * 80}")
        print(title)
        print(f"{'=' * 80}\n")
        if not rows:
            print("No result yet. Run the query when ready.")
            return rows
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def run_query(self, pipeline, ratings=False):
        """Execute a MongoDB pipeline when you are ready."""
        if ratings:
            return list(self.ratings.aggregate(pipeline))
        else:
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
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q2(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            {"$project": {
                "vote_average": 1,
                "cast_pairs": {
                    #Map to create cast_pairs
                    "$map": {
                        "input":"$cast",
                        "as":"c_a",
                        "in": {
                            #Filter to avoid duplicates
                            "$filter":{
                                "input":{
                                    #Map for the second cast of the pair
                                    "$map": {
                                        "input":"$cast",
                                        "as":"c_b",
                                        "in": {
                                            "a":"$$c_a.person_id",
                                            "name_a":"$$c_a.name", 
                                            "b":"$$c_b.person_id", 
                                            "name_b":"$$c_b.name"
                                        }
                                    }
                                },
                                "as":"pair",
                                "cond":{"$gt":["$$pair.a","$$pair.b"]}
                            }
                        }
                    }
                },
            }},

            #Double unwind to get 1 line per cast pair (with movie _id)
            { "$unwind": "$cast_pairs" },
            { "$unwind": "$cast_pairs" },

            #Group per pair and get values
            { "$group": {
                "_id": { "a": "$cast_pairs.a", "b": "$cast_pairs.b" },
                "name_a":{ "$first":"$cast_pairs.name_a"},
                "name_b":{ "$first":"$cast_pairs.name_b"},

                "co_appearance_count": { "$sum":1 },
                "mean_vote_average": { "$avg": "$vote_average" },
            }},

            #Keep only the pairs with more (>=) than 3 co-appereance and order it DSC
            { "$match": { "co_appearance_count": { "$gte": 3 } } },
            { "$sort": { "co_appearance_count": -1 } },

            { "$project": {
                "_id": 0,
                "name_a": 1,
                "name_b": 1,
                "co_appearance_count": 1,
                "mean_vote_average": {"$round": ["$mean_vote_average", 2]},
            }},
            
            {"$limit": 10},
            
        ]

        rows = self.run_query(pipeline)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q3(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            {"$project": {
                "actor_genres": {
                    "$map": {
                        "input":"$cast",
                        "as":"c",
                        "in":{
                            "cast_id":"$$c.person_id", 
                            "cast_name":"$$c.name",
                            "genres":"$genres.name"
                        }
                    }
                }
                
            }},

            { "$unwind": "$actor_genres"},
            { "$unwind": "$actor_genres.genres"},



            { "$group": {
                "_id": "$actor_genres.cast_id",
                "cast": {"$first": "$actor_genres.cast_name"},
                "movies": { "$addToSet": "$_id"},
                "genres": { "$addToSet": "$actor_genres.genres" }
            }},


            { "$set": {
                "movie_count": {"$size": "$movies"},
                "genre_count": {"$size": "$genres"}
            }},

            { "$match": {"movie_count": { "$gte":10 }}},

            { "$sort": {"genre_count":-1}},

            { "$limit": 10},

            { "$project": {
                "_id":0,
                "cast":1,
                "genre_count":1,
                "genres_extract": {"$slice": ["$genres", 5]}
            }}


            
        ]
        
        rows = self.run_query(pipeline)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q4(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            {"$project": {
                "_id":1,
                "revenue":1,
                "collection": 1,
                "vote_average":1,
                "release_date":1
            }},

            # Keepings values with a collection, and a defined revenue
            # Since we want to find the top 10 by total revenue, removing None/0 revenues
            # is not a problem
            { "$match": {"collection.name": {"$ne":None}, "revenue": {"$gt":0}}},

            { "$group": {
                "_id": "$collection.id",
                "name": {"$first":"$collection.name"},
                "movie_count": {"$sum":1},
                "total_revenue": {"$sum":"$revenue"},
                "earliest": {"$min":"$release_date"},
                "latest": {"$max":"$release_date"},
                "median_vote_average": {"$median": {"input": "$vote_average", "method": "approximate"}},

            }},

            { "$match": {"movie_count": {"$gte":3}}},

            { "$sort": {"total_revenue":-1}},

            { "$limit": 10},

            { "$project": {
                "_id":0,
                "name":1,
                "movie_count":1,
                "total_revenue":1,
                "earliest":1,
                "latest":1,
                "median_vote_average":1
            }}

            
        ]
                
        rows = self.run_query(pipeline)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q5(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            {"$project": {
                "_id":1,
                "release_decade":1,
                "runtime":1,
                "first_genre": {"$first":"$genres"}
            }},

            
            # Keepings values with an existing runtime
            { "$match": {"runtime": {"$gt":0}, "first_genre": {"$ne":None}}},

            { "$group": {
                "_id": {"d":"$release_decade", "g":"$first_genre.id"},
                "decade": {"$first":"$release_decade"},
                "genre_name": {"$first":"$first_genre.name"},
                "movie_count": {"$sum":1},
                "median_runtime": {"$median": {"input": "$runtime", "method": "approximate"}},

            }},

            {"$sort": {"decade":-1, "median_runtime":-1}},

            # Just for display purpose
            { "$limit":15},

            { "$project": {
                "_id":0,
                "decade":1,
                "genre_name":1,
                "movie_count":1,
                "median_runtime":1
            }}

        ]
        rows = self.run_query(pipeline)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q6(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            {"$project": {
                "_id":1,
                "release_decade":1,
                "cast": 1
            }},

            { "$unwind": "$cast"},
            
            { "$match": {"release_decade": {"$ne":None}} },
            # Keepings the top 5 billed cast and ignored unknow gender

            { "$match": {"cast.order": {"$lt":5}, "cast.gender": {"$in": [1,2]}} },

            # Calculates the number of female cast per film. We take into account the fact that we may have less than 5 cast members
            { "$group": {
                "_id":"$_id",
                "decade": {"$first":"$release_decade"},
                "female_count": {"$sum": {"$cond": [{"$eq": ["$cast.gender", 1]}, 1, 0]}},
                "cast_count": {"$sum":1}
            }},

            { "$set": {
                "female_proportion": {"$divide":["$female_count","$cast_count"]}
            }},

            { "$group": {
                "_id": "$decade",
                "decade": {"$first":"$decade"},
                "movie_count": {"$sum":1},
                "average_female_proportion": {"$avg":"$female_proportion"}
            }},

            { "$sort": {"average_female_proportion":-1}},

            # Just for display purpose
            { "$limit":15},

            { "$project": {
                "_id":0,
                "decade":1,
                "average_female_proportion":1,
                "movie_count":1
            }}

        ]
                
        rows = self.run_query(pipeline)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q7(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            # Search for the litteral "neo-noir" substring.
            {"$match": {
                "$text": {"$search": "\"neo-noir\""},
                "vote_count": {"$gte": 50}
            }},

            {"$project": {
                "_id": 1, 
                "title": 1, 
                "release_year": 1, 
                "vote_average": 1, 
                "vote_count": 1
            }},

            #Union to run the second text search
            {"$unionWith": {
                "coll": "movies",
                "pipeline": [
                    {"$match": {
                        "$text": {"$search": "noir"},
                        "vote_count": {"$gte": 50}
                    }},
                    {"$project": {
                        "_id": 1, 
                        "title": 1, 
                        "release_year": 1, 
                        "vote_average": 1, 
                        "vote_count": 1
                    }}
                ]
            }},

            {"$group": {
                "_id": "$_id",
                "title": {"$first": "$title"},
                "release_year": {"$first": "$release_year"},
                "vote_average": {"$first": "$vote_average"},
                "vote_count": {"$first": "$vote_count"}
            }},

            {"$sort": {"vote_average": -1}},

            {"$limit": 20},

            {"$project": {
                "_id": 0,
                "title":1,
                "release_year":1,
                "vote_average":1,
                "vote_count":1
                }}
        ]
        rows = self.run_query(pipeline)
        print("\nResults:")
        print(len(rows))
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q8(self):
        """TODO: write the MongoDB query for this question."""
        #I'll reuse some parts of Q2's pipeline.
        pipeline = [
            {"$project": {
                "vote_average": 1,
                "vote_count":1,
                "revenue":1,
                "cast_director_pairs": {
                    #Map to create cast_director_pairs
                    "$map": {
                        "input":"$cast",
                        "as":"ca",
                        "in": {
                            #Filter to avoid duplicates
                            "$filter":{
                                "input":{
                                    #Map for the second crew of the pair
                                    "$map": {
                                        "input":"$crew",
                                        "as":"cr",
                                        "in": {
                                            "cast_id":"$$ca.person_id",
                                            "cast_name":"$$ca.name", 
                                            "director_id":"$$cr.person_id", 
                                            "director_name":"$$cr.name",
                                            "crew_job":"$$cr.job"
                                        }
                                    }
                                },
                                "as":"pair",
                                "cond":{"$gt":["$$pair.cast_id","$$pair.director_id"]}
                            }
                        }
                    }
                },
            }},

            #Double unwind to get 1 line per cast pair (with movie_id)
            { "$unwind": "$cast_director_pairs" },
            { "$unwind": "$cast_director_pairs" },

            #Keep only Director and movies with more than 100 votes.
            { "$match": {"vote_count": { "$gte":100}, "cast_director_pairs.crew_job": {"$eq":"Director"}}},

            { "$group": {
                "_id": {"a":"$cast_director_pairs.cast_id", "b":"$cast_director_pairs.director_id"},

                "cast_name":{ "$first":"$cast_director_pairs.cast_name"},
                "director_name":{ "$first":"$cast_director_pairs.director_name"},

                "collaboration_count": { "$sum":1 },
                "mean_vote_average": { "$avg": "$vote_average" },
                "mean_revenue": { "$avg": "$revenue" }
            }},

            #Keep only the pairs with more (>=) than 3 co-appereance and order it DSC
            { "$match": { "collaboration_count": { "$gte": 3 } } },
            { "$sort": { "vote_average": -1 } },

            { "$project": {
                "_id": 0,
                "director_name": 1,
                "cast_name": 1,
                "collaboration_count": 1,
                "mean_vote_average": {"$round": ["$mean_vote_average", 2]},
                "mean_revenue": 1,

            }},
            
            {"$limit": 20},
                        

            
        ]
        
        rows = self.run_query(pipeline)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q9(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            { "$project": {
                "_id":1,
                "original_title":1,
                "original_language":1,
                "production_countries":1,
            }},

            { "$unwind": "$production_countries"},

            #Get only non english speaking movies producted in the US
            { "$match": {"original_language": {"$ne":"en"}, "production_countries.iso_3166_1": {"$eq":"US"}}},

            { "$group": {
                "_id": "$original_language",
                "language": {"$first":"$original_language"},
                "movie_count": {"$sum":1},
                "example_title": {"$first":"$original_title"},
            }},

            { "$sort": {"movie_count":-1}},

            { "$limit":10},

            { "$project": {
                "_id":0
            }}
        ]
        rows = self.run_query(pipeline)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q10_variance(self):
        """TODO: write the MongoDB query for this question."""
        pipeline = [
            { "$project": {
                "_id":1,
                "user_id":1,
                "rating":1,
            }},

            { "$group": {
                "_id":"$user_id",
                "rating_count": {"$sum":1},
                "std_dev_ratings": {"$stdDevSamp":"$rating"}
            }},

            { "$match": {"rating_count": {"$gte":20}}},

            { "$sort": {"std_dev_ratings":-1}},

            { "$limit":10}
        ]
        rows = self.run_query(pipeline, ratings=True)
        print("\nResults:")
        print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
        return rows

    def q10_genre(self):
            """TODO: write the MongoDB query for this question."""
            pipeline = [
                { "$project": {
                    "_id":1,
                    "user_id":1,
                    "movie_lens_id":1,
                    "rating":1,
                }},

                { "$group": {
                    "_id":"$user_id",
                    "rating_count": {"$sum":1},
                    "movies": {"$push":"$movie_lens_id"}
                }},
    
                # For each user, add movies_genres
                { "$lookup": {
                    "from": "movies",
                    "localField": "movies",
                    "foreignField":"movie_lens_id",
                    "pipeline": [ 
                        { "$project": {
                            "_id":0,
                            "genres":"$genres.name"
                        }},

                    ],
                    "as": "movies_genres"
                }},

                # Here, a double unwind + group (making a set of genres) + set (size of genres)
                # was replaced by this set (reduce) + set (genre_count)
                # I coded the first implementation, that was working but very very slow
                # From my code, AI gave me this more efficient alternative
                { "$set": { 
                    "genres": {
                        "$reduce": {
                            "input": "$movies_genres.genres",
                            "initialValue": [],
                            "in": { "$setUnion": ["$$value", "$$this"] }
                        }
                    }
                }},

                { "$set": { "genre_count": { "$size": "$genres" } } },

                { "$sort": {"genre_count":-1, "rating_count": -1}},

                { "$limit": 10},

                { "$project": {
                    "_id":0,
                    "user_id":"$_id",
                    "genre_count":1,
                    "rating_count":1

                }}

            ]
            rows = self.run_query(pipeline, ratings=True)
            print("\nResults:")
            print(tabulate(rows, headers="keys", tablefmt="grid", missingval="NULL"))
            return rows
    
        

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
    workspace.q10_genre()

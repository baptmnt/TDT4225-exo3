# MongoDB schema keys and types

## `movies` — root fields

| key | type |
| --- | --- |
| `_id` | `Long` |
| `tmdb_id` | `Long` |
| `imdb_id` | `string \| null` |
| `movie_lens_id` | `Long \| null` |
| `title` | `string \| null` |
| `original_title` | `string \| null` |
| `original_language` | `string \| null` |
| `status` | `string \| null` |
| `adult` | `boolean` |
| `video` | `boolean` |
| `release_date` | `date \| null` |
| `release_year` | `int \| null` |
| `release_month` | `int \| null` |
| `release_decade` | `string \| null` |
| `budget` | `double \| null` |
| `revenue` | `double \| null` |
| `runtime` | `double \| null` |
| `popularity` | `double \| null` |
| `vote_average` | `double \| null` |
| `vote_count` | `double \| null` |
| `rating_average` | `double \| null` |
| `rating_count` | `double \| null` |
| `overview` | `string \| null` |
| `tagline` | `string \| null` |
| `homepage` | `string \| null` |
| `poster_path` | `string \| null` |
| `collection` | `object \| null` |

## `movies` — embedded fields

| key | type |
| --- | --- |
| `collection.id` | `Long` |
| `collection.name` | `string` |
| `genres[].id` | `Long` |
| `genres[].name` | `string` |
| `genres[].position` | `int` |
| `production_companies[].id` | `Long` |
| `production_companies[].name` | `string` |
| `production_countries[].iso_3166_1` | `string` |
| `production_countries[].name` | `string` |
| `spoken_languages[].iso_639_1` | `string` |
| `spoken_languages[].name` | `string` |
| `keywords[].id` | `Long` |
| `keywords[].name` | `string` |
| `cast[].person_id` | `Long` |
| `cast[].name` | `string` |
| `cast[].character` | `string` |
| `cast[].order` | `int` |
| `cast[].gender` | `int \| null` |
| `cast[].profile_path` | `string \| null` |
| `crew[].person_id` | `Long` |
| `crew[].name` | `string` |
| `crew[].department` | `string` |
| `crew[].job` | `string` |
| `crew[].gender` | `int \| null` |
| `crew[].profile_path` | `string \| null` |

## `ratings`

| key | type |
| --- | --- |
| `_id` | `ObjectId` |
| `user_id` | `Long` |
| `movie_lens_id` | `Long` |
| `rating` | `double` |
| `rated_at` | `date` |
| `timestamp` | `Long \| null` |

## Notes

- `vote_average` / `vote_count` come from TMDB.
- `rating_average` / `rating_count` come from MovieLens aggregated data.
- `movie_lens_id` is the MovieLens identifier used to join `ratings` to `movies`.
- `tmdb_id` is the TMDB identifier used to join movie metadata and external IDs.

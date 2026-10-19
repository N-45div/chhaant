# The cell end to end (bedrock)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 6a5cf04, iteration 4, three repeats of every crate x order.

| measure | value |
|---|---|
| runs | 96 |
| errors | 3 |
| packed_right | 186 |
| packed_wrong | 0 |
| best_possible | 198 |
| fill | 0.939 |
| wrong_share_of_packed | 0.0 |
| wrong_share_upper_95 | 0.016 |
| wasted_sound | 0 |
| questions_per_run | 3.35 |
| reviews_per_run | 1.88 |
| refused_per_run | 0.26 |
| order_read_right | 93/93 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 26.1 |
| turns_per_run | 7.7 |
| cost_per_run_usd | 0.0392 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 4 | 0 | 5 | 7 | 2 | True | False | 44.3 |  |
| 0 | 0 | 4 | 0 | 5 | 7 | 2 | True | False | 43.7 |  |
| 0 | 0 | 4 | 0 | 5 | 7 | 2 | True | False | 37.5 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 25.2 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 17.4 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 12.8 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 26.7 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 25.5 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 24.5 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 16.0 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 18.3 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 51.4 |  |
| 0 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 14.2 |  |
| 0 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 18.2 |  |
| 0 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 96.8 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 33.2 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 86.3 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 118.2 |  |
| 0 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 37.3 |  |
| 0 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 69.1 |  |
| 0 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 71.5 |  |
| 0 | 7 | 2 | 0 | 2 | 4 | 2 | True | False | 18.2 |  |
| 0 | 7 | 2 | 0 | 2 | 4 | 2 | True | False | 63.7 |  |
| 0 | 7 | 2 | 0 | 2 | 4 | 2 | True | False | 25.7 |  |
| 1 | 0 | 5 | 0 | 5 | 7 | 0 | True | False | 33.4 |  |
| 1 | 0 | 5 | 0 | 5 | 7 | 0 | True | False | 26.1 |  |
| 1 | 0 | 5 | 0 | 5 | 7 | 0 | True | False | 32.5 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 17.4 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 19.3 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 22.0 |  |
| 1 | 2 | 2 | 0 | 2 | 4 | 2 | True | False | 18.3 |  |
| 1 | 2 | 2 | 0 | 2 | 4 | 2 | True | False | 44.2 |  |
| 1 | 2 | 2 | 0 | 2 | 4 | 2 | True | False | 19.8 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 20.5 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 44.8 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 25.3 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 16.3 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 34.0 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 44.1 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 20.5 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 49.6 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 79.1 |  |
| 1 | 6 | 1 | 0 | 1 | 3 | 1 | True | False | 68.3 |  |
| 1 | 6 | 1 | 0 | 1 | 3 | 1 | True | False | 40.0 |  |
| 1 | 6 | 1 | 0 | 1 | 3 | 1 | True | False | 92.7 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 41.6 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 32.1 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 71.5 |  |
| 2 | 0 | 5 | 0 | 5 | 9 | 0 | True | False | 84.9 |  |
| 2 | 0 | 5 | 0 | 5 | 9 | 0 | True | False | 38.7 |  |
| 2 | 0 | 0 | 0 | 5 | 0 | 0 | True | False | 129.2 | ServiceUnavailableException: An error occurred (ServiceUnava |
| 2 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 31.5 |  |
| 2 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 17.0 |  |
| 2 | 1 | 0 | 0 | 2 | 0 | 0 | True | False | 113.1 | ServiceUnavailableException: An error occurred (ServiceUnava |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 17.1 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.5 |  |
| 2 | 2 | 0 | 0 | 2 | 0 | 0 | False | False | 101.4 | ServiceUnavailableException: An error occurred (ServiceUnava |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 17.6 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 14.1 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 29.7 |  |
| 2 | 4 | 1 | 0 | 1 | 4 | 0 | True | False | 14.7 |  |
| 2 | 4 | 1 | 0 | 1 | 4 | 0 | True | False | 19.5 |  |
| 2 | 4 | 1 | 0 | 1 | 4 | 0 | True | False | 25.2 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 23.2 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 23.1 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 34.7 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 17.8 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 17.5 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 17.8 |  |
| 2 | 7 | 1 | 0 | 1 | 6 | 1 | True | False | 35.6 |  |
| 2 | 7 | 1 | 0 | 1 | 6 | 1 | True | False | 23.5 |  |
| 2 | 7 | 1 | 0 | 1 | 6 | 1 | True | False | 33.2 |  |
| 3 | 0 | 3 | 0 | 3 | 10 | 0 | True | False | 67.0 |  |
| 3 | 0 | 3 | 0 | 3 | 9 | 0 | True | False | 37.7 |  |
| 3 | 0 | 3 | 0 | 3 | 10 | 0 | True | False | 42.1 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 25.1 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 14.7 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 22.6 |  |
| 3 | 2 | 1 | 0 | 1 | 5 | 0 | True | False | 49.6 |  |
| 3 | 2 | 1 | 0 | 1 | 5 | 0 | True | False | 28.7 |  |
| 3 | 2 | 1 | 0 | 1 | 5 | 0 | True | False | 31.8 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 12.6 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 15.6 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 17.5 |  |
| 3 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 28.2 |  |
| 3 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 28.5 |  |
| 3 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 14.6 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 0 | True | False | 27.3 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 0 | True | False | 43.3 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 0 | True | False | 30.8 |  |
| 3 | 6 | 2 | 0 | 2 | 3 | 0 | True | False | 21.1 |  |
| 3 | 6 | 2 | 0 | 2 | 3 | 0 | True | False | 29.1 |  |
| 3 | 6 | 2 | 0 | 2 | 3 | 0 | True | False | 21.1 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 20.3 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 19.7 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 21.2 |  |

# The cell end to end (nemotron)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 6a5cf04, iteration 4, a simulated person wrong 10% of the time.

| measure | value |
|---|---|
| runs | 32 |
| errors | 0 |
| packed_right | 56 |
| packed_wrong | 9 |
| best_possible | 69 |
| fill | 0.812 |
| wrong_share_of_packed | 0.138 |
| wrong_share_upper_95 | 0.2292 |
| wasted_sound | 0 |
| questions_per_run | 3.12 |
| reviews_per_run | 2.16 |
| refused_per_run | 0.41 |
| order_read_right | 31/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 37.75 |
| turns_per_run | 13.3 |
| cost_per_run_usd | 0.0 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 3 | 0 | 5 | 9 | 0 | True | False | 53.8 |  |
| 0 | 1 | 2 | 1 | 2 | 3 | 1 | True | False | 22.9 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 23.1 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 24.1 |  |
| 0 | 4 | 0 | 0 | 1 | 2 | 0 | True | False | 17.9 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 23.8 |  |
| 0 | 6 | 1 | 0 | 1 | 2 | 1 | True | False | 23.1 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 13.6 |  |
| 1 | 0 | 5 | 0 | 5 | 6 | 1 | True | False | 169.5 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 33.0 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 28.5 |  |
| 1 | 3 | 2 | 1 | 2 | 3 | 4 | True | False | 177.3 |  |
| 1 | 4 | 0 | 1 | 1 | 0 | 0 | False | False | 45.4 |  |
| 1 | 5 | 3 | 1 | 4 | 5 | 1 | True | False | 55.8 |  |
| 1 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 20.2 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 72.2 |  |
| 2 | 0 | 5 | 0 | 5 | 8 | 0 | True | False | 126.6 |  |
| 2 | 1 | 2 | 1 | 2 | 3 | 1 | True | False | 63.2 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 40.7 |  |
| 2 | 3 | 2 | 0 | 3 | 4 | 0 | True | False | 82.0 |  |
| 2 | 4 | 1 | 0 | 1 | 3 | 0 | True | False | 19.4 |  |
| 2 | 5 | 3 | 1 | 4 | 4 | 1 | True | False | 80.8 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 89.4 |  |
| 2 | 7 | 1 | 0 | 1 | 3 | 0 | True | False | 41.2 |  |
| 3 | 0 | 3 | 2 | 3 | 7 | 1 | True | False | 77.7 |  |
| 3 | 1 | 0 | 0 | 1 | 3 | 0 | True | False | 34.0 |  |
| 3 | 2 | 1 | 0 | 1 | 3 | 0 | True | False | 48.6 |  |
| 3 | 3 | 1 | 1 | 1 | 2 | 1 | True | False | 59.5 |  |
| 3 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 16.3 |  |
| 3 | 5 | 2 | 0 | 3 | 3 | 0 | True | False | 34.8 |  |
| 3 | 6 | 1 | 0 | 2 | 1 | 1 | True | False | 20.3 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 21.6 |  |

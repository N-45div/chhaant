# The cell end to end (nemotron)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 6abb7e2, iteration 4 with the live demo's camera faults (--faults).

| measure | value |
|---|---|
| runs | 32 |
| errors | 0 |
| packed_right | 64 |
| packed_wrong | 0 |
| best_possible | 69 |
| fill | 0.928 |
| wrong_share_of_packed | 0.0 |
| wasted_sound | 0 |
| questions_per_run | 3.03 |
| reviews_per_run | 2.28 |
| refused_per_run | 0.53 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 22.65 |
| turns_per_run | 13.3 |
| cost_per_run_usd | 0.0 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 4 | 0 | 5 | 6 | 0 | True | False | 61.8 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 21.4 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 22.8 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 24.9 |  |
| 0 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 19.3 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 26.5 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 1 | True | False | 21.1 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 15.5 |  |
| 1 | 0 | 5 | 0 | 5 | 6 | 1 | True | False | 57.1 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 21.1 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 14.1 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 27.9 |  |
| 1 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 13.7 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 20.6 |  |
| 1 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 19.3 |  |
| 1 | 7 | 1 | 0 | 1 | 3 | 0 | True | False | 23.0 |  |
| 2 | 0 | 5 | 0 | 5 | 8 | 1 | True | False | 49.1 |  |
| 2 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 18.0 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.9 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 29.4 |  |
| 2 | 4 | 1 | 0 | 1 | 4 | 1 | True | False | 22.5 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 1 | True | False | 36.1 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 19.3 |  |
| 2 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 24.5 |  |
| 3 | 0 | 3 | 0 | 3 | 7 | 0 | True | False | 54.5 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 20.5 |  |
| 3 | 2 | 1 | 0 | 1 | 3 | 0 | True | False | 22.9 |  |
| 3 | 3 | 1 | 0 | 1 | 3 | 1 | True | False | 28.0 |  |
| 3 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 18.0 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 11 | True | False | 75.9 |  |
| 3 | 6 | 1 | 0 | 2 | 1 | 0 | True | False | 18.3 |  |
| 3 | 7 | 1 | 0 | 2 | 3 | 0 | True | False | 30.3 |  |

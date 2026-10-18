# The cell end to end (nemotron)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 3b682e0, iteration 4 (batch review: several items in one glance).

| measure | value |
|---|---|
| runs | 32 |
| errors | 0 |
| packed_right | 66 |
| packed_wrong | 0 |
| best_possible | 69 |
| fill | 0.957 |
| wrong_share_of_packed | 0.0 |
| wasted_sound | 0 |
| questions_per_run | 2.84 |
| reviews_per_run | 1.97 |
| refused_per_run | 0.28 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 24.4 |
| turns_per_run | 12.9 |
| cost_per_run_usd | 0.0 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 5 | 0 | 5 | 8 | 0 | True | False | 71.4 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 36.4 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 23.5 |  |
| 0 | 3 | 2 | 0 | 2 | 4 | 0 | True | False | 30.7 |  |
| 0 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 12.0 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 29.2 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 0 | True | False | 18.1 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 12.5 |  |
| 1 | 0 | 5 | 0 | 5 | 6 | 0 | True | False | 51.6 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 19.2 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 12.6 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 1 | True | False | 31.5 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 14.2 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 23.1 |  |
| 1 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 20.6 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 20.1 |  |
| 2 | 0 | 5 | 0 | 5 | 7 | 1 | True | False | 57.7 |  |
| 2 | 1 | 2 | 0 | 2 | 4 | 0 | True | False | 30.1 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.8 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 24.2 |  |
| 2 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 15.6 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 25.4 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 1 | True | False | 21.7 |  |
| 2 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 25.1 |  |
| 3 | 0 | 3 | 0 | 3 | 6 | 1 | True | False | 59.3 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 1 | True | False | 34.2 |  |
| 3 | 2 | 1 | 0 | 1 | 3 | 0 | True | False | 20.8 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 24.6 |  |
| 3 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 16.0 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 3 | True | False | 49.2 |  |
| 3 | 6 | 1 | 0 | 2 | 1 | 1 | True | False | 24.8 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 26.4 |  |

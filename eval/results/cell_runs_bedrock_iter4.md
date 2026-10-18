# The cell end to end (bedrock)

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
| questions_per_run | 3.25 |
| reviews_per_run | 1.78 |
| refused_per_run | 0.34 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 19.85 |
| turns_per_run | 8.2 |
| cost_per_run_usd | 0.0433 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 5 | 0 | 5 | 8 | 1 | True | False | 45.0 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 22.0 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 32.9 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 19.2 |  |
| 0 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 16.9 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 32.6 |  |
| 0 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 22.7 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 14.8 |  |
| 1 | 0 | 5 | 0 | 5 | 6 | 1 | True | False | 34.9 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 16.1 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 18.4 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 19.5 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 17.9 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 23.6 |  |
| 1 | 6 | 1 | 0 | 1 | 3 | 1 | True | False | 19.9 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 24.4 |  |
| 2 | 0 | 5 | 0 | 5 | 15 | 6 | True | False | 43.1 |  |
| 2 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 16.3 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.7 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 14.2 |  |
| 2 | 4 | 1 | 0 | 1 | 4 | 0 | True | False | 14.6 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 28.4 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 17.4 |  |
| 2 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 19.8 |  |
| 3 | 0 | 3 | 0 | 3 | 6 | 0 | True | False | 38.7 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 16.6 |  |
| 3 | 2 | 1 | 0 | 1 | 4 | 0 | True | False | 29.8 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 12.0 |  |
| 3 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 10.9 |  |
| 3 | 5 | 3 | 0 | 3 | 5 | 2 | True | False | 51.2 |  |
| 3 | 6 | 2 | 0 | 2 | 3 | 0 | True | False | 25.6 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 22.9 |  |

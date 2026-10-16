# The cell end to end (nemotron)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 6fb0733, after iteration 3 (no finishing short with an approved item in the crate).

| measure | value |
|---|---|
| runs | 32 |
| errors | 0 |
| packed_right | 67 |
| packed_wrong | 0 |
| best_possible | 69 |
| fill | 0.971 |
| wrong_share_of_packed | 0.0 |
| wasted_sound | 0 |
| questions_per_run | 2.81 |
| refused_per_run | 0.41 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 21.200000000000003 |
| turns_per_run | 13.9 |
| cost_per_run_usd | 0.0 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 5 | 0 | 5 | 8 | 1 | True | False | 56.8 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 1 | True | False | 27.9 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 21.1 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 20.0 |  |
| 0 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 9.6 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 1 | True | False | 36.1 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 0 | True | False | 16.7 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 13.6 |  |
| 1 | 0 | 5 | 0 | 5 | 6 | 4 | True | False | 56.5 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 19.4 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 12.9 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 22.7 |  |
| 1 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 11.0 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 21.3 |  |
| 1 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 16.4 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 21.1 |  |
| 2 | 0 | 5 | 0 | 5 | 7 | 0 | True | False | 44.1 |  |
| 2 | 1 | 2 | 0 | 2 | 3 | 1 | True | False | 20.4 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.4 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 1 | True | False | 26.2 |  |
| 2 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 13.9 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 1 | True | False | 33.3 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 21.3 |  |
| 2 | 7 | 1 | 0 | 1 | 2 | 1 | True | False | 23.7 |  |
| 3 | 0 | 3 | 0 | 3 | 5 | 0 | True | False | 38.9 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 17.7 |  |
| 3 | 2 | 1 | 0 | 1 | 3 | 0 | True | False | 22.1 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 24.0 |  |
| 3 | 4 | 1 | 0 | 1 | 1 | 1 | True | False | 16.9 |  |
| 3 | 5 | 3 | 0 | 3 | 4 | 1 | True | False | 43.0 |  |
| 3 | 6 | 2 | 0 | 2 | 2 | 0 | True | False | 21.1 |  |
| 3 | 7 | 2 | 0 | 2 | 3 | 0 | True | False | 22.5 |  |

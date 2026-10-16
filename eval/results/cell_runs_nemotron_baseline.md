# The cell end to end (nemotron)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit e8cb4c4, before the Oct 17 fixes (the baseline).

| measure | value |
|---|---|
| runs | 32 |
| errors | 0 |
| packed_right | 54 |
| packed_wrong | 21 |
| best_possible | 69 |
| fill | 0.783 |
| wrong_share_of_packed | 0.28 |
| wasted_sound | 0 |
| questions_per_run | 0.97 |
| refused_per_run | 0.19 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 16.6 |
| turns_per_run | 10.7 |
| cost_per_run_usd | 0.0 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 2 | 1 | 5 | 4 | 1 | True | False | 41.2 |  |
| 0 | 1 | 2 | 1 | 2 | 0 | 0 | True | False | 16.0 |  |
| 0 | 2 | 0 | 2 | 1 | 0 | 0 | True | False | 12.5 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 19.0 |  |
| 0 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 11.6 |  |
| 0 | 5 | 3 | 1 | 4 | 0 | 1 | True | False | 28.7 |  |
| 0 | 6 | 1 | 0 | 1 | 4 | 0 | True | False | 23.7 |  |
| 0 | 7 | 2 | 0 | 2 | 1 | 0 | True | False | 13.3 |  |
| 1 | 0 | 5 | 0 | 5 | 2 | 0 | True | False | 29.8 |  |
| 1 | 1 | 2 | 1 | 2 | 0 | 0 | True | False | 13.8 |  |
| 1 | 2 | 2 | 0 | 2 | 0 | 0 | True | False | 10.7 |  |
| 1 | 3 | 2 | 0 | 2 | 3 | 0 | True | False | 25.8 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 13.3 |  |
| 1 | 5 | 4 | 0 | 4 | 0 | 1 | True | False | 38.4 |  |
| 1 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 18.0 |  |
| 1 | 7 | 1 | 0 | 1 | 1 | 0 | True | False | 16.4 |  |
| 2 | 0 | 3 | 2 | 5 | 1 | 1 | True | False | 28.7 |  |
| 2 | 1 | 2 | 1 | 2 | 0 | 0 | True | False | 11.8 |  |
| 2 | 2 | 2 | 0 | 2 | 1 | 0 | True | False | 11.0 |  |
| 2 | 3 | 3 | 1 | 3 | 1 | 0 | True | False | 17.5 |  |
| 2 | 4 | 0 | 1 | 1 | 0 | 0 | True | False | 8.0 |  |
| 2 | 5 | 3 | 1 | 4 | 0 | 0 | True | False | 17.7 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 15.9 |  |
| 2 | 7 | 0 | 1 | 1 | 1 | 0 | True | False | 18.1 |  |
| 3 | 0 | 3 | 2 | 3 | 1 | 1 | True | False | 36.3 |  |
| 3 | 1 | 1 | 2 | 1 | 0 | 0 | True | False | 12.0 |  |
| 3 | 2 | 1 | 1 | 1 | 1 | 0 | True | False | 13.9 |  |
| 3 | 3 | 0 | 1 | 1 | 1 | 0 | True | False | 15.4 |  |
| 3 | 4 | 0 | 1 | 1 | 0 | 0 | True | False | 7.8 |  |
| 3 | 5 | 3 | 1 | 3 | 0 | 1 | True | False | 21.7 |  |
| 3 | 6 | 1 | 0 | 2 | 1 | 0 | True | False | 16.8 |  |
| 3 | 7 | 1 | 0 | 2 | 1 | 0 | True | False | 18.5 |  |

# The cell end to end (nemotron)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 7df04c7, after iteration 2 (discard only spoiled items; ask before placing; declined items back to the crate).

| measure | value |
|---|---|
| runs | 32 |
| errors | 0 |
| packed_right | 61 |
| packed_wrong | 0 |
| best_possible | 69 |
| fill | 0.884 |
| wrong_share_of_packed | 0.0 |
| wasted_sound | 0 |
| questions_per_run | 2.69 |
| refused_per_run | 0.34 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 22.450000000000003 |
| turns_per_run | 13.6 |
| cost_per_run_usd | 0.0 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 3 | 0 | 5 | 6 | 0 | True | False | 50.2 |  |
| 0 | 1 | 1 | 0 | 2 | 3 | 0 | True | False | 22.8 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 23.6 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 22.1 |  |
| 0 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 11.2 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 1 | True | False | 34.4 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 0 | True | False | 16.4 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 14.4 |  |
| 1 | 0 | 5 | 0 | 5 | 5 | 3 | True | False | 59.7 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 23.4 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 14.7 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 23.4 |  |
| 1 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 12.7 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 1 | True | False | 29.7 |  |
| 1 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 18.9 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 20.9 |  |
| 2 | 0 | 4 | 0 | 5 | 7 | 0 | True | False | 42.7 |  |
| 2 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 20.9 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 12.9 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 1 | True | False | 28.6 |  |
| 2 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 17.2 |  |
| 2 | 5 | 4 | 0 | 4 | 4 | 2 | True | False | 48.1 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 20.4 |  |
| 2 | 7 | 1 | 0 | 1 | 2 | 1 | True | False | 27.5 |  |
| 3 | 0 | 3 | 0 | 3 | 5 | 0 | True | False | 41.2 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 17.7 |  |
| 3 | 2 | 1 | 0 | 1 | 3 | 0 | True | False | 30.6 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 1 | True | False | 29.7 |  |
| 3 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 16.3 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 1 | True | False | 44.1 |  |
| 3 | 6 | 1 | 0 | 2 | 1 | 0 | True | False | 17.2 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 18.5 |  |

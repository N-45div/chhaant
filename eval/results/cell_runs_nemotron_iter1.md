# The cell end to end (nemotron)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 6e31229, after iteration 1 (line-bound questions, ripe-edge rule, validated verdicts, named days, honest finish).

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
| questions_per_run | 3.31 |
| refused_per_run | 0.44 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 22.1 |
| turns_per_run | 13.9 |
| cost_per_run_usd | 0.0 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 4 | 0 | 5 | 7 | 0 | True | False | 65.6 |  |
| 0 | 1 | 2 | 0 | 2 | 4 | 1 | True | False | 22.3 |  |
| 0 | 2 | 1 | 0 | 1 | 4 | 1 | True | False | 29.2 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 20.7 |  |
| 0 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 10.8 |  |
| 0 | 5 | 4 | 0 | 4 | 4 | 1 | True | False | 40.8 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 0 | True | False | 14.0 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 14.6 |  |
| 1 | 0 | 5 | 0 | 5 | 7 | 0 | True | False | 56.8 |  |
| 1 | 1 | 2 | 0 | 2 | 4 | 0 | True | False | 18.9 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.8 |  |
| 1 | 3 | 2 | 0 | 2 | 3 | 0 | True | False | 28.4 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 11.3 |  |
| 1 | 5 | 4 | 0 | 4 | 4 | 2 | True | False | 58.0 |  |
| 1 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 20.5 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 19.4 |  |
| 2 | 0 | 5 | 0 | 5 | 7 | 1 | True | False | 50.9 |  |
| 2 | 1 | 2 | 0 | 2 | 4 | 1 | True | False | 20.9 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.7 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 28.5 |  |
| 2 | 4 | 1 | 0 | 1 | 2 | 1 | True | False | 18.7 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 29.6 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 17.0 |  |
| 2 | 7 | 1 | 0 | 1 | 3 | 1 | True | False | 22.6 |  |
| 3 | 0 | 3 | 0 | 3 | 8 | 1 | True | False | 54.7 |  |
| 3 | 1 | 1 | 0 | 1 | 5 | 1 | True | False | 21.9 |  |
| 3 | 2 | 1 | 0 | 1 | 4 | 1 | True | False | 26.9 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 1 | True | False | 24.9 |  |
| 3 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 13.3 |  |
| 3 | 5 | 3 | 0 | 3 | 5 | 1 | True | False | 36.1 |  |
| 3 | 6 | 2 | 0 | 2 | 2 | 0 | True | False | 22.5 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 17.3 |  |

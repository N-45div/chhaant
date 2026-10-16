# The cell end to end (bedrock)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 6e31229, after iteration 1 (line-bound questions, ripe-edge rule, validated verdicts, named days, honest finish).

| measure | value |
|---|---|
| runs | 32 |
| errors | 0 |
| packed_right | 65 |
| packed_wrong | 0 |
| best_possible | 69 |
| fill | 0.942 |
| wrong_share_of_packed | 0.0 |
| wasted_sound | 3 |
| questions_per_run | 3.75 |
| refused_per_run | 1.19 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 34.55 |
| turns_per_run | 9.3 |
| cost_per_run_usd | 0.0505 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 4 | 0 | 5 | 9 | 4 | True | False | 86.3 |  |
| 0 | 1 | 2 | 0 | 2 | 4 | 1 | True | False | 40.4 |  |
| 0 | 2 | 0 | 0 | 1 | 4 | 2 | True | False | 43.2 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 28.9 |  |
| 0 | 4 | 1 | 0 | 1 | 1 | 1 | True | False | 33.5 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 2 | True | False | 48.6 |  |
| 0 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 33.1 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 42.9 |  |
| 1 | 0 | 5 | 0 | 5 | 7 | 1 | True | False | 75.5 |  |
| 1 | 1 | 2 | 0 | 2 | 4 | 1 | True | False | 32.6 |  |
| 1 | 2 | 2 | 0 | 2 | 4 | 2 | True | False | 34.7 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 20.9 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 14.3 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 35.7 |  |
| 1 | 6 | 1 | 0 | 1 | 4 | 0 | True | False | 36.4 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 24.5 |  |
| 2 | 0 | 5 | 0 | 5 | 9 | 1 | True | False | 44.5 |  |
| 2 | 1 | 2 | 0 | 2 | 4 | 2 | True | False | 35.0 |  |
| 2 | 2 | 2 | 0 | 2 | 4 | 2 | True | False | 31.0 |  |
| 2 | 3 | 3 | 0 | 3 | 5 | 2 | True | False | 31.0 |  |
| 2 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 21.6 |  |
| 2 | 5 | 4 | 0 | 4 | 4 | 1 | True | False | 34.4 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 35.3 |  |
| 2 | 7 | 1 | 0 | 1 | 4 | 2 | True | False | 37.2 |  |
| 3 | 0 | 3 | 0 | 3 | 11 | 4 | True | False | 57.9 |  |
| 3 | 1 | 1 | 0 | 1 | 5 | 2 | True | False | 20.8 |  |
| 3 | 2 | 1 | 0 | 1 | 4 | 1 | True | False | 32.7 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 18.3 |  |
| 3 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 21.7 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 0 | True | False | 37.8 |  |
| 3 | 6 | 2 | 0 | 2 | 2 | 0 | True | False | 24.2 |  |
| 3 | 7 | 1 | 0 | 2 | 7 | 7 | True | False | 65.5 |  |

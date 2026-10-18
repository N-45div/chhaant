# The cell end to end (bedrock)

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
| questions_per_run | 3.56 |
| reviews_per_run | 1.91 |
| refused_per_run | 0.59 |
| order_read_right | 32/32 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 20.75 |
| turns_per_run | 8.2 |
| cost_per_run_usd | 0.0433 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 3 | 0 | 5 | 8 | 3 | True | False | 41.0 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 24.0 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 25.6 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 19.5 |  |
| 0 | 4 | 1 | 0 | 1 | 2 | 2 | True | False | 27.1 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 20.5 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 0 | True | False | 18.1 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 15.6 |  |
| 1 | 0 | 5 | 0 | 5 | 5 | 1 | True | False | 32.3 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 13.1 |  |
| 1 | 2 | 2 | 0 | 2 | 4 | 2 | True | False | 20.2 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 21.0 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 12.2 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 16.3 |  |
| 1 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 19.7 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 17.6 |  |
| 2 | 0 | 5 | 0 | 5 | 16 | 7 | True | False | 44.0 |  |
| 2 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 16.2 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.2 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 24.1 |  |
| 2 | 4 | 1 | 0 | 1 | 4 | 1 | True | False | 19.9 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 23.2 |  |
| 2 | 6 | 1 | 0 | 1 | 4 | 0 | True | False | 25.3 |  |
| 2 | 7 | 1 | 0 | 1 | 6 | 1 | True | False | 30.7 |  |
| 3 | 0 | 3 | 0 | 3 | 10 | 0 | True | False | 40.7 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 13.2 |  |
| 3 | 2 | 1 | 0 | 1 | 4 | 0 | True | False | 30.4 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 14.7 |  |
| 3 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 10.9 |  |
| 3 | 5 | 3 | 0 | 3 | 4 | 1 | True | False | 35.1 |  |
| 3 | 6 | 2 | 0 | 2 | 2 | 0 | True | False | 21.9 |  |
| 3 | 7 | 1 | 0 | 2 | 3 | 1 | True | False | 34.0 |  |

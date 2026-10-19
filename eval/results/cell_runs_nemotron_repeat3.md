# The cell end to end (nemotron)

4 real crates x 8 orders, simulated reviewer, today = Thursday 15 October 2026.
Code: commit 6a5cf04, iteration 4, three repeats of every crate x order.

| measure | value |
|---|---|
| runs | 96 |
| errors | 0 |
| packed_right | 194 |
| packed_wrong | 0 |
| best_possible | 207 |
| fill | 0.937 |
| wrong_share_of_packed | 0.0 |
| wrong_share_upper_95 | 0.0153 |
| wasted_sound | 0 |
| questions_per_run | 2.99 |
| reviews_per_run | 2.06 |
| refused_per_run | 0.15 |
| order_read_right | 96/96 |
| dishonest_summaries | 0 |
| unfinished | 0 |
| median_seconds | 21.3 |
| turns_per_run | 12.6 |
| cost_per_run_usd | 0.0 |

| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 5 | 0 | 5 | 8 | 0 | True | False | 47.7 |  |
| 0 | 0 | 4 | 0 | 5 | 8 | 3 | True | False | 65.2 |  |
| 0 | 0 | 5 | 0 | 5 | 7 | 0 | True | False | 64.7 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 22.3 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 18.7 |  |
| 0 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 24.3 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 22.9 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 21.0 |  |
| 0 | 2 | 0 | 0 | 1 | 2 | 0 | True | False | 26.1 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 27.7 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 18.4 |  |
| 0 | 3 | 1 | 0 | 2 | 2 | 0 | True | False | 25.1 |  |
| 0 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 15.0 |  |
| 0 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 13.9 |  |
| 0 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 10.3 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 26.4 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 27.2 |  |
| 0 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 26.6 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 0 | True | False | 17.6 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 0 | True | False | 17.3 |  |
| 0 | 6 | 1 | 0 | 1 | 1 | 0 | True | False | 18.8 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 13.3 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 14.1 |  |
| 0 | 7 | 2 | 0 | 2 | 2 | 0 | True | False | 14.4 |  |
| 1 | 0 | 5 | 0 | 5 | 5 | 0 | True | False | 39.2 |  |
| 1 | 0 | 5 | 0 | 5 | 6 | 0 | True | False | 40.4 |  |
| 1 | 0 | 5 | 0 | 5 | 5 | 0 | True | False | 41.7 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 19.5 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 18.4 |  |
| 1 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 17.6 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 11.6 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 12.4 |  |
| 1 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 12.1 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 25.4 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 30.0 |  |
| 1 | 3 | 2 | 0 | 2 | 2 | 0 | True | False | 24.3 |  |
| 1 | 4 | 1 | 0 | 1 | 0 | 0 | True | False | 11.4 |  |
| 1 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 15.8 |  |
| 1 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 14.6 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 0 | True | False | 20.1 |  |
| 1 | 5 | 3 | 0 | 4 | 2 | 1 | True | False | 35.7 |  |
| 1 | 5 | 4 | 0 | 4 | 2 | 1 | True | False | 31.9 |  |
| 1 | 6 | 1 | 0 | 1 | 4 | 0 | True | False | 20.1 |  |
| 1 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 20.1 |  |
| 1 | 6 | 1 | 0 | 1 | 2 | 0 | True | False | 16.5 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 19.1 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 20.8 |  |
| 1 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 17.6 |  |
| 2 | 0 | 5 | 0 | 5 | 6 | 0 | True | False | 41.6 |  |
| 2 | 0 | 5 | 0 | 5 | 9 | 1 | True | False | 55.5 |  |
| 2 | 0 | 5 | 0 | 5 | 7 | 0 | True | False | 42.8 |  |
| 2 | 1 | 2 | 0 | 2 | 3 | 1 | True | False | 21.7 |  |
| 2 | 1 | 2 | 0 | 2 | 3 | 0 | True | False | 19.4 |  |
| 2 | 1 | 2 | 0 | 2 | 4 | 0 | True | False | 24.3 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.4 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.7 |  |
| 2 | 2 | 2 | 0 | 2 | 2 | 0 | True | False | 13.4 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 23.0 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 23.4 |  |
| 2 | 3 | 3 | 0 | 3 | 4 | 0 | True | False | 22.1 |  |
| 2 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 15.2 |  |
| 2 | 4 | 1 | 0 | 1 | 4 | 0 | True | False | 18.9 |  |
| 2 | 4 | 1 | 0 | 1 | 5 | 0 | True | False | 21.0 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 23.6 |  |
| 2 | 5 | 4 | 0 | 4 | 4 | 1 | True | False | 40.0 |  |
| 2 | 5 | 4 | 0 | 4 | 3 | 0 | True | False | 24.1 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 1 | True | False | 18.6 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 0 | True | False | 21.3 |  |
| 2 | 6 | 1 | 0 | 1 | 3 | 1 | True | False | 19.1 |  |
| 2 | 7 | 1 | 0 | 1 | 2 | 0 | True | False | 21.3 |  |
| 2 | 7 | 1 | 0 | 1 | 2 | 1 | True | False | 24.1 |  |
| 2 | 7 | 1 | 0 | 1 | 3 | 0 | True | False | 22.2 |  |
| 3 | 0 | 3 | 0 | 3 | 8 | 0 | True | False | 45.9 |  |
| 3 | 0 | 3 | 0 | 3 | 7 | 0 | True | False | 42.4 |  |
| 3 | 0 | 3 | 0 | 3 | 7 | 0 | True | False | 50.9 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 17.7 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 15.9 |  |
| 3 | 1 | 1 | 0 | 1 | 3 | 0 | True | False | 15.8 |  |
| 3 | 2 | 1 | 0 | 1 | 4 | 0 | True | False | 31.0 |  |
| 3 | 2 | 1 | 0 | 1 | 4 | 0 | True | False | 22.5 |  |
| 3 | 2 | 1 | 0 | 1 | 3 | 0 | True | False | 16.5 |  |
| 3 | 3 | 1 | 0 | 1 | 3 | 0 | True | False | 25.2 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 20.7 |  |
| 3 | 3 | 1 | 0 | 1 | 2 | 0 | True | False | 15.4 |  |
| 3 | 4 | 1 | 0 | 1 | 2 | 0 | True | False | 15.3 |  |
| 3 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 13.8 |  |
| 3 | 4 | 1 | 0 | 1 | 1 | 0 | True | False | 14.1 |  |
| 3 | 5 | 3 | 0 | 3 | 4 | 1 | True | False | 37.3 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 0 | True | False | 26.9 |  |
| 3 | 5 | 3 | 0 | 3 | 3 | 0 | True | False | 27.9 |  |
| 3 | 6 | 2 | 0 | 2 | 3 | 0 | True | False | 21.9 |  |
| 3 | 6 | 1 | 0 | 2 | 1 | 1 | True | False | 17.1 |  |
| 3 | 6 | 1 | 0 | 2 | 2 | 1 | True | False | 21.6 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 22.7 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 21.5 |  |
| 3 | 7 | 1 | 0 | 2 | 2 | 0 | True | False | 21.3 |  |

# The cell end to end, iteration by iteration

4 real crates x 8 natural orders per column, scored against the hidden labels (eval/cell_runs.py). The simulated reviewer answers from the labels, so "packed wrong" assumes a person answers correctly.

* **baseline**: the cell as of Oct 16
* **iter1**: questions and approvals bound to one line; avocado packed only if the whole forecast range is ripe in time; verdicts acted on alone only where validated for that produce; the cell counts days to a named day; no 'complete' while short
* **iter2**: a discard needs a spoiled item; ask before placing an 'ask' item; a declined item goes back to the crate
* **iter3**: no finishing short with an approved item still in the crate; each 'ask' line is asked about
* **iter4**: a person reviews several items in one glance (ask_person item_ids); the agent batches per line
* **iter5**: sell-today needs its own question; a yes to a general question permits no move

## Claude Haiku 4.5 on Amazon Bedrock

| | baseline | iter1 | iter2 | iter3 | iter4 | iter5 |
|---|---|---|---|---|---|---|
| packed wrong | 22 | 0 | 0 | 0 | 0 | 0 |
| packed right | 56 | 65 | 64 | 64 | 66 | 66 |
| fill (of the best possible) | 0.812 | 0.942 | 0.928 | 0.928 | 0.957 | 0.957 |
| sound items thrown away | 1 | 3 | 0 | 0 | 0 | 0 |
| questions to a person per run | 1.03 | 3.75 | 2.88 | 2.91 | 3.25 | 3.19 |
| times a person is interrupted per run | 1.03 | 3.75 | 2.88 | 2.91 | 1.78 | 1.66 |
| refused moves per run | 0.09 | 1.19 | 0.19 | 0.19 | 0.34 | 0.34 |
| orders read right | 24/32 | 32/32 | 32/32 | 32/32 | 32/32 | 32/32 |
| 'complete' claimed while short | 4 | 0 | 0 | 0 | 0 | 0 |
| median seconds per run | 29.3 | 34.55 | 28.25 | 23.9 | 19.85 | 45.05 |
| cost per run (USD) | 0.029 | 0.051 | 0.043 | 0.043 | 0.043 | 0.038 |

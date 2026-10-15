# Bad captures: harm and detection

Thresholds from 360 calibration photos (0.5th / 99.5th percentiles of good photos):

| check | threshold |
|---|---|
| min_contrast | 27.4 |
| min_edge_sharpness | 0.1768 |
| max_glare | 0.02 |
| min_backdrop_grey | 135.0 |
| max_item_clipped | 0.05 |
| max_outline_on_edge | 0.02 |

## Held-out photos

On the clean row, "flagged" is the false-alarm rate on good photos.

| condition | photos | flagged | for the right reason | median shift in defect score | view call changed | moved to clean |
|---|---|---|---|---|---|---|
| clean | 360 | 0.8% | - | 0.000 | 0.0% | 0.0% |
| defocus 1.5 | 360 | 42.2% | 42.2% | 0.008 | 26.7% | 20.6% |
| defocus 3 | 360 | 95.6% | 95.6% | 0.012 | 28.3% | 22.8% |
| motion 9 | 360 | 30.6% | 30.6% | 0.013 | 25.0% | 12.2% |
| motion 17 | 360 | 84.4% | 84.4% | 0.017 | 32.2% | 21.1% |
| glare 10% | 360 | 98.9% | 98.9% | 0.009 | 19.4% | 10.6% |
| glare 20% | 360 | 99.4% | 99.4% | 0.009 | 23.6% | 11.1% |
| dark x0.2 | 360 | 100.0% | 100.0% | 0.342 | 68.9% | 17.5% |
| bright x3 | 360 | 99.4% | 98.9% | 0.057 | 37.8% | 12.5% |
| empty | 360 | 100.0% | 97.8% | 0.033 | 39.4% | 35.3% |
| cut off 40% | 360 | 100.0% | 100.0% | 0.032 | 23.9% | 1.7% |

False alarms on good TR-6 photos: 3 of 240.

False alarms on good avocado photos: 0 of 120.

Safety: good photos of spoiled TR-6 fruit flagged 1 of 66 (fresh fruit: 2 of 174). A flag here would hide a defect behind "bad photo".

## Which blur measure separates sharp from blurred (held-out AUC)

| blur | outline sharpness | interior texture |
|---|---|---|
| defocus 1.5 | 0.956 | 0.980 |
| defocus 3 | 0.994 | 0.999 |
| motion 9 | 0.949 | 0.855 |
| motion 17 | 0.982 | 0.925 |

Spoiled TR-6 views that a failure turned into a "clean" call: 105 of 660; the checks flag 95 of those 105.

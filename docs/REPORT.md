# Chhaant: a produce-picking cell that knows what its camera cannot see

*Technical report for the OpenCV AI Competition 2026.* Chhaant (छाँट, Hindi for picking out the best from a pile) is an
inspection-and-picking cell for online grocery orders. A language-model agent reads a customer's order, an OpenCV 5
vision pipeline inspects each item on a turntable, a decision layer works out what each item is fit for, and a robot
arm (simulated) packs, holds back, sells today or rejects it. When the vision is not trustworthy for a call, the cell
asks a person, and it can say why with a number measured on held-out data.

Live: <https://d1lk9oj2so3zh7.cloudfront.net> (AWS, Graviton4 with the Cloud-Optimized OpenCV Library).

![Architecture](architecture.svg)

## 1. Results at a glance

| What | Result | Where |
|---|---|---|
| End to end: wrong items packed for a customer, 32 orders x 2 language models | 22 and 21 at the start, **0 and 0** after four measured iterations | §7.1 |
| End to end: share of what the crate could have filled, packed correctly | 81% / 78% at the start, **96% / 96%** now | §7.1 |
| Times a person is interrupted per order (the price of the safety) | 1.8 (Claude Haiku 4.5), 2.0 (Nemotron 3 Super) | §7.1 |
| Rotate until sure vs looking at all 16 angles, 312 held-out sessions | **38 wrong calls vs 69**, with 3.95 views instead of 16 | §5.1 |
| Avocado shelf life from two photos + temperature, 426 held-out fruit | mean error **1.05 days** (temperature alone: 3.45) | §5.2 |
| Sequential crate acceptance vs the fixed sampling plan | **38–79 items inspected instead of 135**, same risks | §5.4 |
| Capture checks on held-out photos | 0.8% false alarms; catch 95 of the 105 spoiled views a bad photo turned "clean" | §4.5 |
| COOL vs the PyPI wheel on the same Graviton4; Graviton4 vs x86 | same speed, same readings; Graviton4 30–41% cheaper per item | §8.2 |

## 2. The problem

Produce is where online grocery disappoints: in a 2023 LocalCircles survey of Indian consumers, about 73% said the fresh
produce they ordered online was of low quality ([Inc42](https://inc42.com/?p=427056)). Picking is done by people in dark stores at speed,
and the decisions a careful shopper makes in the aisle (turn the tomato over; buy the firm avocado for Saturday and the
soft one for tonight) do not survive that speed. No robot I found chooses produce by quality for an individual order;
existing systems sort by grade on a conveyor or pick by position.

The decision is harder than "good or bad":

* a defect may be on the side the camera does not see, so one photo is not enough;
* "good" depends on when the food will be eaten: a rock-hard avocado is a fine choice for Saturday and a bad one for
  tonight;
* for a whole supplier crate, the question is whether to accept the lot, and inspecting everything is wasteful;
* some calls the camera simply cannot make, and the system must know which.

### 2.1 Users

* **The picker at the cell** (in a dark store or a store's back room) answers the cell's questions: one review card per
  order line, each item's photos and the reason the cell cannot decide alone. They are the human in control.
* **The customer** writes the order in plain words ("an avocado for Saturday's brunch") and gets items chosen for the
  day they will eat them, with a summary that says plainly when a line is short.
* **The store operator** watches the CloudWatch dashboard and alarms (failed runs, a burst of unusable photos, an
  unhealthy instance) and reads any run's evidence in S3.
* **A buyer receiving supplier crates** uses the sequential acceptance test (§5.4) to accept or reject a lot with far
  fewer inspections than a fixed sampling plan.

## 3. System

The cell (top half of the diagram) runs once per order:

1. The **agent** reads the order into lines (produce, quantity, when it will be eaten). The cell, not the model, turns
   a named day ("Saturday") into a number of days.
2. For each candidate item the agent calls **inspect**. The cell turns the item on the turntable, photographs it, and
   runs the OpenCV 5 pipeline on every capture (§4). The decision layer (§5) fuses the views, forecasts shelf life where
   that is validated, and returns a routing for every open order line: pack, skip, sell today, reject, or ask.
3. The agent acts with **place** or **ask_person**. The cell's rules are code, not prompt: nothing is placed before it is
   inspected, a defective item never goes into an order (a person cannot override that), packing needs a "pack"
   routing or a person's approval for that item *and that line*, a sound item is never discarded without a person,
   and **finish** is refused while a short line still has an unexplored candidate or an approved item left in the crate.
4. Every step is written to a JSONL trace; the web page shows it live, with each item's photos as evidence.

![Agent workflow: one order](agent_workflow.svg)

The tools the model sees are `read_order`, `list_crate`, `inspect`, `look_closer`, `ask_person`, `place` and
`finish` (`chhaant/agent/tools.py`). Two models are supported through the same tools: Claude Haiku 4.5 on Amazon
Bedrock (the deployment) and NVIDIA Nemotron 3 Super on Nebius Token Factory.

**Data.** The camera replays real photos: *TriModal Ripeness 6* (TR-6; one fruit each of banana, carrot, guava, Indian
gooseberry (amla), mango and tomato, photographed daily until spoiled from 16 angles at about 40° elevation plus one
overhead view, 3 sessions a day, 5,338 photos) and the *Hass avocado ripening dataset* (478 fruit at 10 °C, 20 °C and
room temperature, two side photos per fruit per day until the end of shelf life). The underside is never
photographed; every "clean" call states the uninspected share.

**The arm** is a Robot Studio SO-101 simulated in MuJoCo (Menagerie model), driven by inverse kinematics. Its motion is
simulated; the pixels every decision uses are real photographs. The page shows the arm in 3D (three.js), streamed from
the MuJoCo twin on the server.

## 4. Vision with OpenCV 5

All image work is OpenCV 5 (`opencv-python` 5.0.0.93 for development, COOL 5.1.0-dev on Graviton in deployment).

### 4.1 Segmentation (`chhaant/vision/segment.py`)

The backdrop colour is estimated from the image border in CIELAB (`cvtColor` to `COLOR_BGR2Lab` on float data). A pixel
is item when its chroma differs from the backdrop, or its lightness differs beyond a shadow tolerance, so the soft
shadow under a fruit is ignored while a blackened fruit is still found. Otsu thresholding (`threshold` with
`THRESH_OTSU`), morphological opening and closing, the largest connected component (`connectedComponentsWithStats`) and
hole filling (`floodFill`) give the mask; `grabCut` is the fallback when the result is implausible. It runs at 512 px
and scales the mask back. It segmented 5,338 of 5,338 TR-6 photos.

### 4.2 Colour (`chhaant/vision/color.py`)

White balance from the backdrop: the median of the backdrop pixels (read off `calcHist` histograms, exact and fast at
12 MP) sets per-channel gains. Colour statistics are medians in CIELAB with hue angle, chroma, the a\*/b\* tomato
maturity index and the share of dark spots. A ColorChecker path (`cv2.mcc` + `cv2.ccm`) exists for cells with a chart;
two OpenCV 5.0.0 behaviours I hit are noted in §11.

### 4.3 Quality model (`chhaant/vision/model.py`, `kaggle/train/`)

A MobileNetV3-Large with two heads (defect probability, ripeness 0–1), trained on a Kaggle GPU on five public datasets
(tomato quality, tomato maturity, African plums, a conveyor-belt fruit defect set, banana ripeness; 8,019 training
images). **TR-6 and the avocado set were held out entirely.** The item is cropped from the mask with the backdrop
greyed out (`chhaant/vision/crop.py`, shared by training and inference) so the model looks at the produce, not the
scene. Normalisation is inside the ONNX graph, so OpenCV feeds raw RGB through `dnn.blobFromImages`.

The model runs on OpenCV 5's **new DNN engine** (`readNetFromONNX(..., ENGINE_NEW)`). Against PyTorch, the largest
difference is 2.6e-6 (defect) and 1.2e-5 (ripeness) on `ENGINE_NEW`, and 2.1e-6 / 9.8e-6 on `ENGINE_CLASSIC`. Validation
on the training datasets: tomato defect AUC 1.00 (a near-duplicate leak is possible), conveyor 0.999, plums 0.94,
tomato maturity 0.999, banana ripeness Spearman 0.93.

### 4.4 Transfer to the cell's photos

On TR-6, which the model never saw, detecting a spoiled session from the worst of its 16 views:

| AUC, 16 views | banana | carrot | guava | amla | mango | tomato | pooled |
|---|---|---|---|---|---|---|---|
| quality model (OpenCV DNN) | 1.00 | 0.95 | 0.95 | 0.79 | 0.71 | **0.59** | 0.86 |
| classical defect map (OpenCV only) | 1.00 | 0.95 | 0.79 | 0.63 | 0.65 | **0.24** | 0.72 |

The learned model wins where it matters, but **tomato is at chance**. The ten spoiled TR-6 tomato sessions look fresh
in RGB from most angles (one has a visible bruise the model scores 0.00); the classical map is even inverted there,
because fresh tomatoes' stem scars read as defects. I did not tune this away: §6 explains what the cell does instead.

### 4.5 Capture checks (`chhaant/vision/capture.py`)

A blurred, glared, badly exposed or empty photo still gets a score from the model, and that score is noise. Every
capture is measured first at the segmentation's working size: outline sharpness (Sobel gradients across the item's
outline over the item/backdrop contrast), glare (pixels blown out in every channel inside the item's convex hull),
overexposure (item clipping not explained by glare), backdrop darkness, the share of the outline on the frame edge, and
the item's contrast with the backdrop. A failed photo is never evidence: the inspection looks elsewhere, and three
failures in a row stop it ("check the cell").

One rule was learned the hard way: **no check may turn a dark or smooth rotten fruit into "bad photo"**. Exposure is
judged on the backdrop, never the item, and surface texture is not a blur test, because both early versions flagged sharp
photos of spoiled fruit.

Calibrated on half of 720 real photos and tested on the other half plus ten synthetic failures
(`eval/capture_failures.py`, run on a 16-core Graviton4):

| Held-out photos | flagged | moves the view's call | of which into "clean" |
|---|---|---|---|
| good photos (false alarms) | 0.8% | – | – |
| defocus σ=3 / motion 17 px | 96% / 84% | 28% / 32% | 23% / 21% |
| defocus σ=1.5 / motion 9 px | 42% / 31% | 27% / 25% | 21% / 12% |
| glare on 10% / 20% of the item | 99% / 99% | 19% / 24% | 11% / 11% |
| 5x darker / 3x brighter | 100% / 99% | 69% / 38% | 18% / 13% |
| empty turntable | 100% | 39% | 35% |
| item 40% out of frame | 100% | 24% | 2% |

Sharp photos of spoiled fruit are flagged at the same rate as fresh ones (1 of 66 vs 2 of 174). Of the 105 spoiled
views a bad capture turned into a "clean" call, the checks flag 95. Mild blur is caught least; it also moves scores
least. A gallery is in `eval/results/capture_failures_gallery.jpg`.

## 5. Decisions

### 5.1 Rotate until sure (`chhaant/decide/policy.py`, `fusion.py`, `chhaant/vision/views.py`)

After every view the policy decides: **defective** when neighbouring views agree (the median of the captured views
within ±45°, at least three); **clean** only when enough of the surface is covered (a coverage map on a sphere; TR-6's
17 views can see at most 67% of a fruit), every suspicious view has been cross-checked from a neighbouring angle, and
the agreed score is low; otherwise it turns the item to the angle that resolves a suspicion or covers the most new
surface, and **escalates** to a person when the view budget runs out. Thresholds were picked leave-one-fruit-out.

| 312 held-out TR-6 sessions | wrong calls | handed to a person | views per item |
|---|---|---|---|
| one view | 78 (25.0%) | 0 | 1 |
| all 16 views (max or agreement) | 69 (22.1%) | 0 | 16 |
| **rotate until sure** | **38 (12.2%)** | 51 | **3.95** |

### 5.2 Shelf life (`chhaant/decide/forecast.py`, `shelf.py`)

A ridge model of log(20 °C-equivalent days left) on colour and model features from the two side photos, with the
temperature dependence learned as one Q10 factor and an 80% interval calibrated on held-out fruit. Five folds grouped by
fruit, 426 avocados, 7,070 fruit-days:

| Forecaster | mean error (days) | within 1 day |
|---|---|---|
| constant | 3.52 | 18% |
| temperature only | 3.45 | 34% |
| vision only | 1.58 | 57% |
| **vision + temperature** | **1.05** (10 °C 1.39, 20 °C 0.56, room 0.51) | **64%** |

Q10 = 2.66 ± 0.05; the 80% interval covers 81% of held-out fruit; one side photo is as good as two (1.06). The same
idea did **not** transfer across TR-6's produce (guava error 13 days, banana and mango worse than a constant), so the
cell offers no shelf-life number for them: a forecast is only shown where it was validated.

### 5.3 Routing per order line (`chhaant/decide/route.py`)

Defective → reject. Undecided → a person. Sound but gone within a day → sell today. For produce eaten ripe (avocado),
an item is packed only when its **whole forecast interval** says it lasts until the eating day and is ripe by then; an
interval that crosses either edge goes to a person; one wholly too firm or wholly gone is kept for another order.

### 5.4 Crate acceptance (`chhaant/decide/lot.py`)

For a supplier crate, Wald's sequential probability ratio test (good ≤ 5% defective vs bad ≥ 20%, both risks 5%), with
the robot's measured error rates and hand-offs modelled jointly. Simulated on 2,000 crates of 400 items per defect rate:
it inspects **38–79 items instead of the fixed plan's 135** with 4–10 person checks instead of 15–22, and keeps its
promises (accepts a 5% crate 97.0% of the time, a 20% crate 4.4%). Modelling the hand-offs mattered: ignoring them made
the test accept good crates only 88% of the time.

## 6. Appropriate autonomy: knowing what the camera cannot see

A clean verdict is acted on alone only if validation says it can be (`chhaant/agent/inspectors.py`): for each produce,
the leave-one-fruit-out results give how often rotate-until-sure called a spoiled item clean and a fresh item defective.
Above 10%, the verdict goes to a person with the measured reason, which the agent passes on: "for tomato this
inspection missed 10 of 10 spoiled ones in validation". Banana's defective calls are confirmed the same way (it wrongly
rejected 9 of 9 fresh ones). This is the change that took wrong packs to zero (§7.1). It costs questions, so a person
reviews all the items that need them for an order line **in one glance**, each answer still binding only its own item
and line.

The resulting split of autonomy is explicit and measured. The cell acts alone on: banana, carrot and guava "clean"
calls (no spoiled one missed in validation), tomato, mango, amla and guava "defective" calls (no fresh one wrongly rejected),
and avocados whose whole forecast interval fits the eating day. A person decides: tomato, mango and amla "clean" calls,
banana and carrot "defective" calls, avocados whose interval crosses an edge, and anything the inspection could not
decide or the camera could not photograph properly.

## 7. Evaluation

### 7.1 The whole cell, end to end (`eval/cell_runs.py`)

Four real crates (TR-6 tomatoes and mangoes, some spoiled; avocados with known days left) times eight everyday orders
("4 avocados for guacamole tonight", "an avocado for Saturday's brunch and one mango", "one tomato for a sandwich and
one avocado for next Wednesday"...). Each order has a hand-written gold reading; every run is scored against the
dataset's hidden labels, never seen by the agent. A simulated reviewer answers questions from the labels, so "packed
wrong" assumes a person answers correctly. Fill compares correct packs with the most the crate could have filled
correctly (a bipartite matching of fit items to order slots).

I used it as a loop: measure, explain every wrong pack from the trace (`eval/explain_wrong.py`), fix the cause, measure
again.

| Claude Haiku 4.5 (Bedrock) | baseline | iter 1 | iter 2 | iter 3 | iter 4 |
|---|---|---|---|---|---|
| packed wrong | 22 | 0 | 0 | 0 | 0 |
| fill | 81% | 94% | 93% | 93% | 96% |
| sound items thrown away | 1 | 3 | 0 | 0 | 0 |
| times a person is interrupted per order | 1.0 | 3.8 | 2.9 | 2.9 | 1.8 |
| orders read right | 24/32 | 32/32 | 32/32 | 32/32 | 32/32 |
| "complete" claimed while a line is short | 4 | 0 | 0 | 0 | 0 |
| median seconds / cost per order | 29 / $0.029 | 35 / $0.051 | 28 / $0.043 | 24 / $0.043 | 20 / $0.043 |

| Nemotron 3 Super (Nebius) | baseline | iter 1 | iter 2 | iter 3 | iter 4 |
|---|---|---|---|---|---|
| packed wrong | 21 | 0 | 0 | 0 | 0 |
| fill | 78% | 96% | 88% | 97% | 96% |
| times a person is interrupted per order | 1.0 | 3.3 | 2.7 | 2.8 | 2.0 |
| orders read right | 32/32 | 32/32 | 32/32 | 32/32 | 32/32 |

What each iteration changed, and the failure that drove it:

* **Baseline.** 14 of 21 wrong packs were spoiled tomatoes and mangoes inspected as clean (the model scores 0.00 on all
  16 views of every spoiled tomato); 7 were avocados packed for tonight while 5–7 days from ripe. The agent never broke
  a rule; the cell's own decisions were wrong.
* **Iteration 1.** Validated-verdict gating (§6); the whole-interval avocado rule (§5.3); questions and approvals bound
  to one order line (before, "OK for Saturday?" was judged as if for tonight, and an approval unlocked any line); the
  cell counts days to a named day (Haiku read "Monday" as 3 days from a Thursday in all four crates); finish refuses a
  summary that calls a short order complete.
* **Iteration 2.** Haiku discarded avocados a person had declined for one line; declined items now go back to the
  crate, and a discard needs a spoiled item.
* **Iteration 3.** Nemotron finished with person-approved items still in the crate; finish now refuses that. Bedrock
  throttling had killed 9 of 32 runs; calls now back off adaptively (0 errors since).
* **Iteration 4.** Batch review: interruptions 2.9 → 1.8 and 2.8 → 2.0 with no loss.

**With camera faults.** The same 32 orders with the live demo's faults switched on (a motion-blurred view on one
tomato, glare at every angle on another, one avocado side cut off by the frame):

| iteration 4, faults on | packed wrong | fill | unusable photos caught | interruptions per order |
|---|---|---|---|---|
| Claude Haiku 4.5 | 0 | 93% (96% without faults) | 77 | 1.9 (1.8) |
| Nemotron 3 Super | 0 | 93% (96%) | 74 | 2.3 (2.0) |

No unusable photo was ever scored, and the glared tomato went to a person and was still packed when sound. The few
items lost were avocados the agent allocated differently between lines (A2's forecast now comes from one side),
within the run-to-run variation noted in §11.

**Repeated, and with an imperfect person.** Iteration 4 rerun three times on every crate and order (96 orders per
model), and once more with a simulated person who gives the wrong answer 10% or 20% of the time:

| | orders | items packed | packed wrong | 95% upper bound on the wrong rate | fill | interruptions per order |
|---|---|---|---|---|---|---|
| Claude Haiku 4.5, 3 repeats | 96 (3 ended by Bedrock "service unavailable" after 10 retries) | 186 | 0 | 1.6% | 94% | 1.9 |
| Nemotron 3 Super, 3 repeats | 96 | 194 | 0 | 1.5% | 94% | 2.1 |
| Nemotron, person wrong 10% of the time | 32 | 65 | 9 (14%) | – | 81% | 2.2 |
| Nemotron, person wrong 20% of the time | 32 | 67 | 11 (16%) | – | 81% | 2.3 |

The zero rests on the person: almost every mistaken "yes" became a wrong pack, because for tomatoes the camera has no
signal that could contradict it. The cell still does better than acting on its own verdicts (28% wrong in the
baseline), but the honest claim is that it puts the decisions it cannot make in front of a person, with the evidence;
it does not make the person unnecessary.

### 7.2 Failure cases

Failures I found and what the cell does about them (each is a test in `tests/`):

| Failure | Found by | Now |
|---|---|---|
| Spoiled tomato invisible to the model (AUC 0.59) | transfer evaluation, end-to-end runs | a person confirms every tomato, with the measured reason |
| TR-6 "spoiled" mango is over-ripe, not rotten (defect ≈ 0, ripeness 0.90) | real-session trace | ripeness reported; mango gated like tomato |
| Avocado forecast 2.25 days (1.41–3.61), truly 7 | end-to-end runs | interval crossing the ripe edge goes to a person |
| Blur, glare, darkness, empty turntable, item out of frame | capture evaluation | photo never scored; three in a row stop the inspection |
| A flag hides a rotten fruit behind "bad photo" | calibration (spoiled amla flagged as blurred) | exposure on the backdrop; no texture-based blur test |
| "avocados" vs "Avocado": 20 placements refused in one live run | live run | the cell maps names to its own (case, plurals, "amla") |
| "Saturday" counted as 5 days by a model; "Saturday" on a Saturday read as 7 | end-to-end and live runs | the cell counts; today's weekday means today |
| Model writes "Order complete" with a line short | end-to-end runs | finish refused until the summary says what is short |
| Bedrock ThrottlingException ends an order | end-to-end runs | adaptive retries, up to 10 attempts |

## 8. AWS

### 8.1 Deployment (`deploy/`)

One CloudFormation stack in ap-south-1: an EC2 **c8g.large (Graviton4) running the COOL AMI**, an Elastic IP, and a
CloudFront distribution in front; the instance's security group admits only CloudFront's origin-facing addresses. The
instance role calls **Bedrock** (no keys on disk), writes each run's trace and result to **S3**, and publishes run
metrics to **CloudWatch**, with a dashboard, alarms (failed runs, a burst of unusable photos, failed status checks) and
EC2 auto-recovery. Deploys go through **Systems Manager** (no SSH). Heavy evaluations and the benchmark run on
throwaway Graviton instances that terminate themselves (`deploy/eval_job.sh`, `deploy/bench.sh`). The running stack costs
about $2 a day.

### 8.2 COOL benchmark (`eval/bench_cool.py`, `eval/results/bench_cool.md`)

The cell's own OpenCV calls on a real 4000x3000 camera frame, median ms (2 vCPUs each):

| | c8g + COOL | c8g + PyPI wheel | c7i (x86) + PyPI wheel |
|---|---|---|---|
| GaussianBlur 5x5 | 7.2 | 7.6 | 47.7 |
| BGR→Lab, 8-bit | 18.5 | 18.6 | 47.4 |
| BGR→Lab, float, item window | 13.9 | 13.9 | 25.3 |
| resize to 512 (INTER_AREA) | 17.8 | 17.7 | 24.7 |
| one whole look on a camera frame | 390 | 390 | 398 |
| cost per 1,000 items (3.95 looks each) | $0.027 | $0.023 | $0.039 |

Graviton4 with Arm KleidiCV is 1.4–6.6x faster than Sapphire Rapids with IPP on these calls and 30–41% cheaper per item.
COOL and the PyPI wheel are the same speed on the same machine and give identical readings, because the aarch64 wheel
also ships KleidiCV (a newer version, 26.03, than COOL's 0.7.0). Profiling for this benchmark found that my own numpy
code, not OpenCV, dominated a 12 MP look; moving it to OpenCV calls on the item's window cut a camera-frame look from
about 1.4 s to 0.25 s on the development laptop, with bit-identical output (`tests/test_vision_fast_paths.py`).

### 8.3 Evidence that COOL runs the core workload

* **Deployment:** EC2 c8g.large (Graviton4, Neoverse V2) in ap-south-1, from the COOL Marketplace AMI
  `ami-05a336eb12c47d427`; the app runs in COOL's Python 3.12 venv with COOL's own `cv2`.
* **Version:** `cv2.__version__` is `5.1.0-dev`; `getBuildInformation()` reports `Custom HAL: YES (carotene (ver 0.0.1)
  KleidiCV (ver 0.7.0))` and baseline `SVE NEON FP16 NEON_DOTPROD NEON_FP16 NEON_BF16`.
* **Enforced, not assumed:** the bootstrap (`deploy/bootstrap.sh`) refuses to finish unless the loaded OpenCV reports
  KleidiCV, and never installs the PyPI OpenCV wheel on the server. The live site's `/api/health` returns the build
  line, so anyone can check which OpenCV is doing the vision.
* **Everything in §4 runs on it:** segmentation, colour, capture checks and the quality model on the new DNN engine,
  for every inspection on the live site. The benchmark in §8.2 measures the same calls on the same build.

## 9. Agentic vision: a real trace

The award asks for evidence that OpenCV 5 output changes what the agent does next. This is a recorded run from the
end-to-end evaluation, unedited except for shortening (full file: `docs/traces/avocado-and-mango.jsonl`). The order is
"An avocado for Saturday's brunch and one mango", on a Thursday, Claude Haiku 4.5:

| t (s) | step | what happened |
|---|---|---|
| 2.0 | read_order | the agent passes `eat_on: "Saturday"`; the cell answers "Avocado, eat in 2.0 days; Mango, no timing" |
| 5.8 | inspect M4 | OpenCV pipeline over several views: clean on everything seen, 43% unseen; validation gate: "A person confirms: for mango this inspection missed 3 of 8 spoiled ones in validation"; routing for line 2: **ask** |
| 6.0 | inspect A1 | both side photos measured; forecast 4.6 days (3.2–7.0); routing for line 1: **ask** (may not be ripe in 2 days) |
| 9.3 | ask_person | the agent puts both to the person in one review, but as a general "question" |
| 11.3 | place M4, place A1 | **refused by the cell**: a general question is not permission to pack; each refusal quotes the vision's reason |
| 13.4 | ask_person | the agent asks again, now "pack M4 into line 2" and "pack A1 into line 1"; both approved |
| 15.8 | place | M4 and A1 packed |
| 18.3 | finish | both lines filled; the hidden labels agree both were right |

Every decision after 5.8 s follows from what the cameras measured: the vision's verdicts and forecast intervals set
the routings, the routings set what the cell would allow, and the agent's next calls changed to fit. (The first,
wrong kind of question is the agent's mistake, and the cell's rule caught it.)

## 10. Responsible use

* **People stay in control of what the camera cannot judge.** The cell packs on its own only verdicts validated for
  that produce; everything else is put to a person with the measured reason and the photos. It never discards a sound
  item without a person, and a person cannot force a defective item into an order.
* **No overclaiming.** Each inspection states what was measured and what was not (the uninspected underside, "no
  shelf-life number for this produce"). The safety result is reported with its dependency on the person (§7.1).
* **Not a food-safety test.** The cell judges visible quality and ripeness. It does not detect pathogens, residues or
  internal rot, and it does not replace food-safety checks.
* **Waste.** Sound items that fit no order line go back to the crate; items near the end of their life are routed to
  "sell today" rather than the bin.
* **Privacy.** The camera looks at a turntable; the system stores produce photos, order text and its own decisions,
  with no accounts and no personal data. Evidence goes to a private S3 bucket with public access blocked.
* **Security and cost control.** No keys on disk (instance role), the origin accepts only CloudFront, deploys go
  through Systems Manager without SSH, IAM is scoped to the bucket prefixes and the one Bedrock model, and runs are rate
  limited per visitor and per day because each one calls a paid model.
* **Data and models.** Training and test data are public datasets used under their licences and credited below; the
  model was trained on other regions' produce, and its transfer limits are measured and shown (§4.4).
* **Work.** The cell is designed to take routine judgement calls off a fast-moving picker and leave the hard ones
  with them, with evidence, not to remove the human check.

## 11. Limitations

* **Simulation.** The arm and turntable are simulated; the photos are real but recorded. A live camera would add
  lighting and motion I have only synthesised (§4.5).
* **One fruit per type in TR-6.** Its per-produce numbers rest on one fruit followed for days; the avocado numbers rest
  on 426 fruit. Tomato defect detection is at chance on TR-6, so the cell treats it as unvalidated.
* **The person must answer correctly.** "0 wrong packs" uses a reviewer that answers from the labels; with one wrong
  10–20% of the time, 14–16% of packed items were wrong (§7.1). A person at the cell should turn the item over: the
  camera never sees the underside either.
* **Small end-to-end set.** 4 crates x 8 orders per model (96 orders with repeats); differences of a few percent
  between iterations are within run-to-run variation.
* **OpenCV 5.0.0 behaviours I worked around:** `mcc::CCheckerDetector` found a perfect synthetic chart in only 40–70%
  of attempts regardless of seed or threads (the code retries); `ccm` `correctImage` expects BGR while the fit uses RGB, which
  doubled the colour error until I swapped channels.

## 12. Reproducing

```bash
pip install -r requirements.txt          # pinned: opencv-python 5.0.0.93, numpy 2.4.3, mujoco 3.15.0, ...
pytest                                   # 235 tests
python kaggle/prep/prep.py               # TR-6 photos (range reads from figshare)
python scripts/fetch_avocado.py          # avocado photos (Mendeley)
python scripts/fetch_so101.py            # SO-101 model (MuJoCo Menagerie)
python -m chhaant.web                    # the web app on http://127.0.0.1:8000
python eval/cell_runs.py --backend bedrock        # the end-to-end evaluation (§7.1)
python eval/rotate_until_sure.py ...              # §5.1; every eval/ script documents its inputs
bash deploy/deploy.sh                    # the AWS stack (needs an AWS login and the COOL subscription)
```

Checked on 20 October 2026 from a fresh export of the repository on Ubuntu 24.04 (WSL) with Python 3.12 and only the
pinned requirements: 206 tests pass after `scripts/fetch_so101.py`; the 4 still skipped need the TR-6 photos or the model
file. The quality model (`models/chhaant_quality_v1.onnx`, 12.9 MB) is trained by `kaggle/train/train.py`; *its download
link will be added here.* All results quoted are files in `eval/results/`.

## Where each required item is

| Required | Where |
|---|---|
| Problem, users | §2, §2.1 |
| Architecture (OpenCV 5, AWS, COOL, agent) | diagram at the top, `docs/architecture.svg`; agent workflow `docs/agent_workflow.svg` (§3) |
| OpenCV 5 implementation | §4, `chhaant/vision/` |
| AWS deployment | §8.1, `deploy/` |
| Evaluation, failure cases, limitations | §7, §11, `eval/results/` |
| Responsible use | §10 |
| Pinned dependencies; build, deploy, test steps | `requirements.txt`, §12, `README.md` |
| Working endpoint | <https://d1lk9oj2so3zh7.cloudfront.net> |
| COOL: version, instance, evidence, baseline | §8.2, §8.3, `eval/results/bench_cool.md` |
| Agentic vision: workflow diagram, trace, task success, failure handling, observability, human control | `docs/agent_workflow.svg`, §9, §7.1, §4.5, §8.1, §6 |

## Credits

TriModal Ripeness 6 (figshare, doi:10.6084/m9.figshare.30783827, CC BY 4.0); Hass avocado ripening dataset (Mendeley
Data 3xd9n945v8, CC BY 4.0); tomato maturity and quality, banana ripeness, African plums and conveyor fruit-defect
datasets on Kaggle (CC BY 4.0, CC BY-SA 4.0, CC0); Robot Studio SO-101 from MuJoCo Menagerie (Apache 2.0). Code under
the Apache License 2.0.

# COOL benchmark (20261014-193911)

## Machines and builds

| run | instance | CPU | OpenCV | custom HAL | threads | numpy |
|---|---|---|---|---|---|---|
| c8g-cool | c8g.large | CPU part: 0xd4f | 5.1.0-dev | YES (carotene (ver 0.0.1) KleidiCV (ver 0.7.0)) | 2 | 2.5.1 |
| c8g-pip | c8g.large | CPU part: 0xd4f | 5.0.0 | YES (carotene (ver 0.0.1) KleidiCV (ver 26.03)) | 2 | 2.5.1 |
| c7i-pip | c7i.large | model name: Intel(R) Xeon(R) Platinum 8488C | 5.0.0 | YES (ipp (ver 0.0.1)) | 2 | 2.4.3 |

## OpenCV calls

| OpenCV call, one look, on a real 4000x3000 frame (median ms) | c8g-cool | c8g-pip | c7i-pip | COOL vs wheel, same c8g |
|---|---|---|---|---|
| imdecode camera JPEG | 69.9 | 67.5 | 84.3 | 0.97x |
| resize INTER_AREA to the 512 work size | 17.8 | 17.7 | 24.7 | 0.99x |
| cvtColor BGR2GRAY | 1.94 | 1.88 | 3.41 | 0.97x |
| cvtColor BGR2Lab, 8-bit | 18.5 | 18.6 | 47.4 | 1.00x |
| cvtColor BGR2Lab, float, item window (colour stats) | 13.9 | 13.9 | 25.3 | 1.00x |
| GaussianBlur 5x5 | 7.17 | 7.60 | 47.7 | 1.06x |
| dilate 31x31, item window (white balance) | 24.4 | 24.7 | 24.3 | 1.01x |
| calcHist backdrop median, 3 channels (white balance) | 26.2 | 26.4 | 23.2 | 1.01x |
| erode 7x7, item window (colour stats) | 1.20 | 1.20 | 1.17 | 0.99x |
| resize mask INTER_NEAREST to full size | 3.04 | 2.96 | 3.52 | 0.97x |
| findContours on the full mask | 1.29 | 1.41 | 1.82 | 1.10x |
| item_crop to 224 for the model | 182.5 | 184.9 | 175.2 | 1.01x |
| threshold Otsu at work size | 0.07 | 0.11 | 0.11 | 1.64x |
| imencode JPEG q85 at work size (photo route) | 0.52 | 0.52 | 0.33 | 1.01x |

## Whole looks and the model (median ms)

| step | c8g-cool | c8g-pip | c7i-pip |
|---|---|---|---|
| look on a 512-px photo (the deployed app) | 19.3 | 18.1 | 19.1 |
| look on a camera frame (decode, segment, model) | 390.4 | 389.5 | 398.3 |
| avocado reading on a camera frame (adds white balance + colour) | 565.7 | 561.7 | 619.5 |
| quality model, 1 crop, ENGINE_NEW | 10.1 | 8.65 | 8.72 |
| quality model, 1 crop, ENGINE_CLASSIC | 10.3 | 9.72 | 12.4 |
| quality model, batch of 8, ENGINE_NEW | 77.1 | 65.4 | 68.7 |

## Cost of inspecting 1,000 items

One process per instance, OpenCV's default threads, 3.95 camera-frame looks per item (the rotate-until-sure average). c8g's 2 vCPUs are 2 physical cores; c7i's are 1 core with 2 hyperthreads.

| run | per hour (EC2 + COOL fee) | ms per look | items per hour | per 1,000 items |
|---|---|---|---|---|
| c8g-cool | $0.0640 | 390.4 | 2,335 | $0.0274 |
| c8g-pip | $0.0540 | 389.5 | 2,340 | $0.0231 |
| c7i-pip | $0.0892 | 398.3 | 2,288 | $0.0390 |

## Same answers?

Largest difference in any reading, over 12 camera frames and 48 512-px photos.

| builds | L | a | b | chroma | dark_frac | hue_deg | p_defect | p_defect (512 px) | p_ripeness | p_ripeness (512 px) |
|---|---|---|---|---|---|---|---|---|---|---|
| c8g-cool vs c8g-pip | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| c8g-cool vs c7i-pip | 0 | 0 | 0 | 0 | 0 | 0 | 2e-05 | 0.0019 | 0 | 5e-05 |

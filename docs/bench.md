# Benchmark

Run on Linux x86_64, 12 CPUs, Python 3.14.10, NumPy 2.5.4; seed 1; each time is the median of 5 runs; command `bench --sizes 10000,100000,300000,1000000 --repeat 5 --draws 50 --seeds 50 --out /out`.

## 1. Analysis time by inventory size

Inventories of 120 months of history, synthetic, with the facility sized to hold them. The time covers everything: series, racks, forecast and the 'how many more fit' search. *Literal implementation* is the time of the loop-by-loop Python version on a small inventory, scaled to each size: an extrapolation, not a measurement.

| Devices | Racks | Time | Devices per second | Literal implementation (extrapolated) | Speed-up |
|---|---|---|---|---|---|
| 10,000 | 171 | 134.2 ms | 74,540 | 981.4 ms | 7x |
| 99,852 | 1,701 | 451.6 ms | 221,118 | 9.80 s | 22x |
| 300,082 | 5,103 | 1.30 s | 231,115 | 29.45 s | 23x |
| 999,670 | 17,007 | 1.81 s | 552,785 | 98.11 s | 54x |

The literal implementation analyses 3,094 devices in 303.6 ms (10,189 devices per second).

## 2. Simulating, reading and writing

| Step | Devices | Time | Devices per second |
|---|---|---|---|
| Simulate 11 years of a data center with its truth | 1,479 | 52.3 ms | 28,306 |
| Write the inventory CSV text | 686 | 2.3 ms | 297,696 |
| Parse and validate the inventory CSV text | 686 | 3.3 ms | 207,566 |

## 3. Forecast accuracy against the truth, over 50 synthetic data centers

Seeds 1 to 50; each facility is simulated for 132 months and analysed as of month 36, 48, 60, 72 (only what was installed by then is visible). That is 600 resource and date pairs; 95 were already over their limit and are left out. Of the 505 forecasts: 351 give a month for a crossing that really happens, 14 correctly say there is none within the simulated future, 14 miss a crossing, 126 announce one that does not happen.

Error is the forecast months until the limit minus the true months. Over all 351 estimates: median absolute error 9.6 months, 95th percentile 39.7, median signed error -2.1; the true month is inside the 90% interval in 76.9% of them.

| How far ahead the crossing really is | Estimates | Median abs. error (months) | 95th percentile | Median signed error | Inside the interval |
|---|---|---|---|---|---|
| 1-12 months | 88 | 3.7 | 24.0 | 1.1 | 87.5% |
| 13-24 months | 96 | 9.4 | 28.7 | 0.9 | 85.4% |
| 25-48 months | 120 | 11.6 | 30.9 | -4.8 | 75.0% |
| 49+ months | 47 | 28.8 | 65.3 | -28.8 | 44.7% |

| Resource | Estimates | Median abs. error (months) | 95th percentile | Median signed error | Inside the interval |
|---|---|---|---|---|---|
| Space | 106 | 13.5 | 60.9 | -10.1 | 59.4% |
| Power | 124 | 7.4 | 25.4 | 0.7 | 84.7% |
| Cooling | 121 | 7.5 | 32.5 | -0.4 | 84.3% |

## 4. Agreement with the literal implementation

51 comparisons (a simulated facility and 50 random facilities with random policy): 12,714 numbers compared. Largest relative difference 8.20e-14 (tolerance 1e-09); all match.

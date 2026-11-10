# Analysis

Source: [`report.json`](report.json) (the demo data center: 24 racks, simulated for 60 months, seed 1) and
[`bench.json`](bench.json) (one run in Docker on Linux x86_64 with 12 CPUs, Python 3.14.10, NumPy 2.5.4; medians of 5 runs; 50 simulated
data centers for the accuracy). **The data centers are synthetic**: their projects, devices, lifetimes and plants are drawn from a
generator chosen to be plausible, not measured. Read the structure of the results, not the kilowatts.

## 1. The demo data center today

As of 2024-12: 557 devices in 24 racks of 42 U (1,008 U), a UPS with 281.4 kW usable and a cooling plant with 216.0 kW usable (a
spare unit of each already taken out).

| Resource | Measured as | Used | Capacity | Utilization | Limit | Room to the limit |
|---|---|---|---|---|---|---|
| Space | rack units in use | 745.0 U | 1,008.0 U | 73.9% | 90% | 162.2 U |
| Power | allocated power (nameplate x 0.8) | 204.2 kW | 281.4 kW | 72.6% | 80% | 20.9 kW |
| Cooling | heat (measured draw) | 131.3 kW | 216.0 kW | 60.8% | 85% | 52.3 kW |

- **The resource with the least room is not the one with the highest utilization.** Space is the fullest (73.9%) but has 162 U to
  go; power is at 72.6% of a lower limit and has 20.9 kW to go, about 75 1U servers.
- **Allocated power is 1.56 times the measured draw.** Planning on the nameplate is the safe habit, and it is why the power limit
  is the one that binds here while the cooling, planned on the draw, has room.
- **The racks could draw 288 kW, 1.02 times the usable power.** The rack feeds add up to more than the UPS can give: the data
  center is oversubscribed across racks, which is fine only as long as the racks are not all full at once.

## 2. Racks and stranded capacity

18 of the 24 racks are almost full (36 to 42 U used, 9.9 to 12.0 kW of 12 kW allocated) and 6 are empty. Free space and free power
are in different places:

- **3 free rack units** sit in racks with too little power left for even the smallest standard device (0.24 kW): they cannot be used.
- **9.1 kW of rack power** is left in racks that have no free unit: it cannot be used either.

This is what the totals hide. 162 U to the space limit is not 162 U of devices you can install.

## 3. How many more fit

First fit, one model at a time, under the same limits (the count stops at 1,000):

| Model | Size | Allocated power | Heat | More that fit | Stopped by |
|---|---|---|---|---|---|
| sw-1u | 1 U | 0.24 kW | 0.15 kW | 87 | power capacity |
| srv-1u | 1 U | 0.28 kW | 0.18 kW | 74 | power capacity |
| srv-2u | 2 U | 0.60 kW | 0.38 kW | 34 | power capacity |
| stor-2u | 2 U | 0.48 kW | 0.32 kW | 43 | power capacity |
| gpu-4u | 4 U | 1.60 kW | 1.10 kW | 13 | power capacity |

Every model is stopped by the power capacity, with 6 empty racks standing there. Adding 10 gpu-4u takes the power to 78.2% of
a limit of 80%; adding 10 srv-1u every month, the plan lasts 1 full month, and a second month fits 7 before the power stops it
(`dccap plan --add gpu-4u=10 --monthly srv-1u=10`).

## 4. The forecast

A line and an exponential are fitted to the last 24 months of each resource, and the better one is kept. For the demo:

| Resource | Model | Growth | Reaches the limit | In months | Interval (months) |
|---|---|---|---|---|---|
| Space | exponential | +1.47% a month | 2026-05 | 16 | 3 to 30 |
| Power | exponential | +1.48% a month | 2025-10 | 9 | 1 to 18 |
| Cooling | exponential | +1.40% a month | 2027-03 | 27 | 6 to 47 |

Because this data center is synthetic, we can look at what happened next. Power actually reached its limit after 21 months and
space after 28; the forecasts were 9.3 and 16.4, early by about 12 months each (the space interval holds the truth, the power one
does not). Cooling never reached its limit in the 72 simulated months, yet it was forecast at 27. All three forecasts say "sooner",
and that is a pattern, not luck (next section).

## 5. Over 50 data centers

Seeds 1 to 50; each data center is simulated for 132 months and analysed as of month 36, 48, 60 and 72, seeing only what was installed
by then. That is 600 resource and date pairs; 95 were already over their limit and are left out. Of the 505 forecasts:

| Outcome | Count |
|---|---|
| A month is forecast for a crossing that really happens (an *estimate*) | 351 |
| Correctly no crossing within the simulated future | 14 |
| The crossing happens and the forecast does not announce one | 14 |
| A crossing is announced and does not happen in the simulated future | 126 |

Over the 351 estimates the median absolute error is 9.6 months, the 95th percentile 39.7 and the worst 80.1; the median signed
error is -2.1 months (a little early). The true month is inside the 90% interval 76.9% of the time.

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

- **The forecast is good for two years and weak after that.** A limit 1 to 12 months away is forecast within 3.7 months (median) and
  the interval holds 87.5% of the time; at 13 to 24 months the median error is 9.4 and the coverage 85.4%. Beyond 48 months the median
  error is 28.8 months and the true month is inside the interval less than half the time. The "90%" interval is closer to an 86% one for the next two years
  (159 of the 184 estimates at 1 to 24 months).
- **The far cases are early.** In the 49+ bucket the median signed error equals minus the median absolute error:
  at least half of them are forecast too soon, by the whole error. A limit that is far away is a limit that growth did not reach at the rate it had in the
  window; the trend looks forward from a period of faster growth.
- **Space is the weak resource.** Its coverage is 59.4% and its signed error -10.1 months, against 84 to 85% and under 1 month for
  power and cooling. Space is a resource the facility can fill unevenly: racks run out of power before they run out of units, so the
  aggregate 90% of the units may not be reachable at all.
- **126 false alarms, 61 within 24 months.** A forecast that says "this limit is coming in under 2 years" and is wrong in 61 of 505
  cases is the cost of a method that sees only growth. The generator retires devices (lifetimes around 66 months) and turns away
  what does not fit, so growth slows; the forecast, fitted to the last 24 months, does not know that. A real planner reads the
  forecast next to the retirement calendar and the order book.
- **14 missed crossings**, where the forecast says there is none and the data center does reach the limit. They are the other side of
  the same coin: a slow recent growth that picks up later.
- **Linear or exponential makes a small difference.** Exponential fits are slightly more accurate (median error 8.0 months against
  10.2), and the two cover 75.0% and 78.8%.

### Improving the interval was tried and did not pay

The interval is the first-passage time of a random walk with the measured drift and month-to-month spread (section 4 of
[`method.md`](method.md)). Before this form it was a slope standard error, which covered 17% of the cases, and one widened for
autocorrelation, 34%. During development three further changes were tried on seeds 1 to 20 and checked on seeds 21 to 40:

- **A longer or shorter window** (12, 36, 48 months instead of 24) did not improve the coverage.
- **A cohort model that retires devices** at their expected lifetime gave a lower median error and many more missed crossings,
  with a lot more code. It was not adopted.
- **Extra width for the trend itself** raised the coverage by about 3 to 4 points overall and left the far cases poor.

The limit is not the width of the interval. It is that the point forecast is early when growth saturates, and a wider interval
cannot compensate for a bias.

## 6. Speed

| Devices | Racks | Time | Devices per second | Literal implementation (extrapolated) | Speed-up |
|---|---|---|---|---|---|
| 10,000 | 171 | 134.2 ms | 74,540 | 981.4 ms | 7x |
| 99,852 | 1,701 | 451.6 ms | 221,118 | 9.80 s | 22x |
| 300,082 | 5,103 | 1.30 s | 231,115 | 29.45 s | 23x |
| 999,670 | 17,007 | 1.81 s | 552,785 | 98.11 s | 54x |

- **A hundred times more devices costs 13 times more time.** The time covers everything, and most of it is the
  "how many more fit" search (5 models, up to 1,000 placements each), which depends on the number of racks and not on the
  number of devices; that is why the rate in devices per second rises with the size.
- **The plain Python implementation does 10,189 devices a second** on 3,094 devices, so the NumPy one is 7 to 54 times faster (the
  Python figure is a measurement on a small inventory, scaled to each size). The literal version is there to be obviously right.
- **Reading is not the bottleneck at this scale**: parsing and validating the inventory runs at 207,566 devices a second, and
  writing it at 297,696.
- **The two agree.** 51 comparisons, 12,714 numbers, largest relative difference 8.20e-14, tolerance 1e-09.

## 7. What this does not show

- It does not show that the forecast suits a real data center. The synthetic one grows steadily with a seasonal wobble; real
  growth comes in steps (a migration, a customer) and the 24-month window could be dominated by one of them.
- It does not model airflow or per-rack cooling: cooling is the heat of the devices against a plant capacity, as a first screening.
- It does not show how good the interval is beyond what is counted here: at the dates tested (36 to 72 months of history) and with
  the generator's own lifetimes and growth.

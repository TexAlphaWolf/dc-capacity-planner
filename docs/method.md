# Method

The analysis is implemented twice: vectorised in [`pipeline.py`](../src/dccapacity/pipeline.py) and device by device in
[`reference.py`](../src/dccapacity/reference.py). Months are counted from the `start` of the facility; a device is installed from its
`installed` month (included) to its `removed` month (excluded), or for ever.

## Policy

| Parameter (`dccap analyze` option) | Default | Meaning |
|---|---|---|
| `derate` | 0.8 | Power is allocated as the nameplate times this |
| `space_limit` | 0.90 | Share of the rack units that may be used |
| `power_limit` | 0.80 | Share of the usable UPS capacity that may be allocated |
| `cooling_limit` | 0.85 | Share of the usable cooling capacity that the heat may reach |
| `window` | 24 | Months of history the forecast is fitted to |
| `min_history` | 6 | Fewest months a forecast is made from |
| `z` | 1.645 | Width of the interval in standard deviations (1.645 is 90%) |
| `horizon` | 120 | Months ahead beyond which a crossing is not reported |

The validity rules are in [`params.py`](../src/dccapacity/params.py): the four shares are above 0 and at most 1, `min_history` is at
least 3, `window` is at least `min_history`, `z` and `horizon` are positive, and every number is finite.

## The three resources

| Resource | Used | Capacity |
|---|---|---|
| Space | rack units in use | all rack units |
| Power | allocated power: the sum of nameplate x `derate` over the installed devices | usable UPS: `(units - redundant) x unit_kw` |
| Cooling | heat: the sum of the measured average draw (`avg_w`), all of it turning into heat | usable cooling: `(units - redundant) x unit_kw` |

The utilization of month *m* is the used amount of month *m* over the capacity. The monthly series is built from the install and
removal months without a loop over months per device (a `bincount` and a cumulative sum in the NumPy version; a running total in
the plain one).

## The forecast

For each resource separately:

1. **History.** The last `window` months (fewer if the history is shorter). With fewer than `min_history`, the status is *short
   history* and nothing is forecast.
2. **Already over.** If the last month is at or above the limit, the status is *crossed* and the time left is 0.
3. **Two models.** A line `u = a + b t`, and an exponential, a line fitted to `ln u` (only when every month is above zero). Both
   are least squares. The exponential is kept only if its sum of squared errors, in utilization, is lower than the line's.
4. **No growth.** A slope of zero or less: the status is *no growth*, nothing is forecast.
5. **Crossing.** The time at which the fitted model reaches the limit (the logarithm of the limit for the exponential), counted from
   the last month and never below 0. A crossing more than `horizon` months ahead is not reported (*beyond horizon*).
6. **Interval.** The months to the crossing are the first-passage time of a random walk with drift. With `m` the number of months
   in the window, `d` the distance still to cover (in `u` or in `ln u`), `slope` the fitted drift and `var` the variance of the
   month-to-month increments of the series (of `u`, or of `ln u` for the exponential) seen in the window, the standard deviation of the
   time is

       sd = sqrt( d * var / slope^3  +  (d / slope^2)^2 * var / m )

   The first term is the randomness of the walk itself, the second the uncertainty of the drift estimated from `m` months. The
   interval is the crossing plus and minus `z` x `sd`; its lower end is never below 0.

This is a trend forecast: it sees the growth of the window and nothing else (see [`limitations.md`](limitations.md)).

## Racks and stranded capacity

A rack table lists, for each rack, the units used, the **largest free block** (the longest run of consecutive free units: a 4 U
device needs 4 in a row), the power allocated and the heat. Two kinds of capacity are *stranded*:

- **space**: the free units of racks whose remaining power (rack power minus allocated) is below the allocation of the smallest
  catalog device, 0.24 kW;
- **power**: the remaining rack power of racks with no free unit at all.

## How many more fit

A catalog model is placed one device after another, first fit, until one does not fit; the count is the number placed (it stops at
1,000, reported as "1,000+"). The checks are made in this order, and the first to fail is the reason reported:

1. **cooling**: heat so far plus the device's heat is above `cooling_limit` x usable cooling;
2. **power**: allocated so far plus the device's is above `power_limit` x usable power;
3. **space**: used units plus its height is above `space_limit` x all units;
4. then the search in racks, in rack order and from the lowest unit: a rack qualifies when it has a free block of the height of the
   device and enough rack power left. If no rack has a block, the reason is **space**; if racks have a block but none has the power,
   **rack_power**.

| Model | Height | Nameplate | Typical draw | Allocated (x 0.8) |
|---|---|---|---|---|
| sw-1u | 1 U | 300 W | 150 W | 0.24 kW |
| srv-1u | 1 U | 350 W | 180 W | 0.28 kW |
| srv-2u | 2 U | 750 W | 380 W | 0.60 kW |
| stor-2u | 2 U | 600 W | 320 W | 0.48 kW |
| gpu-4u | 4 U | 2,000 W | 1,100 W | 1.60 kW |

**`plan --add`** places the devices of the request in that order and reports how many fit and the utilization after. **`plan
--monthly`** adds the same devices every month, in the order given, until one does not fit: it reports the full months that fit,
how many fit in the next one and what stopped it, up to `horizon` months.

## The synthetic truth

[`generate.py`](../src/dccapacity/generate.py) simulates a data center month by month. A facility is drawn from the seed: 24 racks of
42 U and 12 kW, and two plants of 3 units with 1 spare each (a power unit of 110 to 170 kW and a cooling unit of 70 to 110 kW), so
every seed has different capacities. The facility starts with 25% of its units used. Each month a Poisson number of projects arrives,
with a rate of 1.1 a month growing 1.1% a month with a yearly seasonality; 3% of the projects are large (15 to 40 devices), the others are
small. Devices are drawn from a catalog mix with their own nameplate and draw (nameplate within 10%, draw within 30% of the catalog
value), placed first fit, and retired after a lifetime of about 66 months (normal, standard deviation 14, at least 24). A device that does
not fit (the plants at 100% of their capacity, no free block, the rack out of power) is turned away and counted.

The truth is the utilization of each resource for all 132 months (60 of history and 72 of future by default). The analysis sees the
inventory as it was at a chosen month; the months after are only used to score the forecast. Two bookkeepings are kept apart: the
simulator's running totals, and the sums the analysis makes from the inventory; they must agree.

## Scoring

[`score.py`](../src/dccapacity/score.py) takes one resource at one date. It is left out if the resource is already at its limit. The
true time is the first later month at which the true utilization reaches the limit, or none within the simulated future. A forecast
beyond the simulated future cannot be checked and counts as "no crossing". Each case is one of:

- **estimate**: both the forecast and the truth have a crossing; the error is forecast minus true months, and the case is *covered*
  if the true month is inside the interval;
- **agree_no_crossing**: neither has one;
- **missed**: the truth crosses and the forecast says there is no crossing;
- **false_alarm**: the forecast crosses (within the simulated future) and the truth does not.

Errors and coverage are summarised overall, by resource, by forecast model and by how far ahead the crossing really is (1 to 12, 13 to
24, 25 to 48, 49 or more months). The sweep simulates seeds 1 to *N* and analyses each as of months 36, 48, 60 and 72.

## Verification

[`verify.py`](../src/dccapacity/verify.py) runs both implementations on a simulated facility and on random facilities (racks of
different sizes, devices overlapping nothing, plants of random size, random policy) and compares every number of the result: floats to
a relative error of 1e-9 (measured against the larger of the two values and 1e-6), everything else exactly.

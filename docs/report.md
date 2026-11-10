# Capacity report: Synthetic data center

Source: demo data center (synthetic, 60 months, seed 1). As of 2024-12 (month 59): 557 devices installed in 24 racks (1,008 U), usable power 281.4 kW, usable cooling 216.0 kW (spare units already taken out). Policy: use at most 90% of the space, 80% of the power and 85% of the cooling; power is allocated at 80% of nameplate.

## 1. Where things stand

| Resource | Measured as | Used | Capacity | Utilization | Limit | Room to the limit |
|---|---|---|---|---|---|---|
| Space | rack units in use | 745.0 U | 1,008.0 U | 73.9% | 90% | 162.2 U |
| Power | allocated power (nameplate x derate) | 204.2 kW | 281.4 kW | 72.6% | 80% | 20.9 kW |
| Cooling | heat (measured draw) | 131.3 kW | 216.0 kW | 60.8% | 85% | 52.3 kW |

The racks could draw 288 kW between them, 1.02 times the usable power: power is oversubscribed across racks. The power allocated is 1.56 times what the devices actually draw.

## 2. When each resource reaches its limit

A line and an exponential are fitted to the last 24 months and the one that follows the data more closely is kept. The interval is the crossing time plus and minus 1.645 standard deviations (90%) of how long a random walk with that drift and the month-to-month spread seen in the window takes to cover the remaining distance. Crossings later than 120 months are not reported.

| Resource | Model | Growth | Reaches the limit | In months | Interval (months) | Note |
|---|---|---|---|---|---|---|
| Space | exponential | +1.47% a month | 2026-05 | 16 | 3 to 30 |  |
| Power | exponential | +1.48% a month | 2025-10 | 9 | 1 to 18 |  |
| Cooling | exponential | +1.40% a month | 2027-03 | 27 | 6 to 47 |  |

First to run out: power, in about 9 months.

## 3. Racks

| Rack | Units used | Largest free block | Allocated power | Heat | Power left in the rack |
|---|---|---|---|---|---|
| R01 | 42 of 42 | 0 U | 11.6 of 12.0 kW | 7.3 kW | 0.4 kW |
| R03 | 42 of 42 | 0 U | 11.8 of 12.0 kW | 7.7 kW | 0.2 kW |
| R04 | 42 of 42 | 0 U | 11.9 of 12.0 kW | 7.5 kW | 0.1 kW |
| R05 | 42 of 42 | 0 U | 11.3 of 12.0 kW | 7.5 kW | 0.7 kW |
| R07 | 42 of 42 | 0 U | 11.0 of 12.0 kW | 7.2 kW | 1.0 kW |
| R08 | 42 of 42 | 0 U | 10.9 of 12.0 kW | 7.6 kW | 1.1 kW |
| R10 | 42 of 42 | 0 U | 11.1 of 12.0 kW | 7.3 kW | 0.9 kW |
| R11 | 42 of 42 | 0 U | 10.1 of 12.0 kW | 6.6 kW | 1.9 kW |
| R12 | 42 of 42 | 0 U | 11.7 of 12.0 kW | 7.3 kW | 0.3 kW |
| R13 | 42 of 42 | 0 U | 11.5 of 12.0 kW | 7.0 kW | 0.5 kW |
| R15 | 42 of 42 | 0 U | 11.9 of 12.0 kW | 7.3 kW | 0.1 kW |
| R16 | 42 of 42 | 0 U | 11.4 of 12.0 kW | 7.0 kW | 0.6 kW |
| R17 | 42 of 42 | 0 U | 10.8 of 12.0 kW | 6.9 kW | 1.2 kW |
| R02 | 41 of 42 | 1 U | 12.0 of 12.0 kW | 8.0 kW | 0.0 kW |
| R06 | 41 of 42 | 1 U | 11.8 of 12.0 kW | 7.8 kW | 0.2 kW |
| R14 | 41 of 42 | 1 U | 11.9 of 12.0 kW | 7.9 kW | 0.1 kW |
| R09 | 40 of 42 | 2 U | 11.6 of 12.0 kW | 7.5 kW | 0.4 kW |
| R18 | 36 of 42 | 6 U | 9.9 of 12.0 kW | 6.1 kW | 2.1 kW |
| R19 | 0 of 42 | 42 U | 0.0 of 12.0 kW | 0.0 kW | 12.0 kW |
| R20 | 0 of 42 | 42 U | 0.0 of 12.0 kW | 0.0 kW | 12.0 kW |
| R21 | 0 of 42 | 42 U | 0.0 of 12.0 kW | 0.0 kW | 12.0 kW |
| R22 | 0 of 42 | 42 U | 0.0 of 12.0 kW | 0.0 kW | 12.0 kW |
| R23 | 0 of 42 | 42 U | 0.0 of 12.0 kW | 0.0 kW | 12.0 kW |
| R24 | 0 of 42 | 42 U | 0.0 of 12.0 kW | 0.0 kW | 12.0 kW |

## 4. Stranded capacity

3 free rack units sit in racks with too little power left for even the smallest standard device; 9.1 kW of rack power is left in racks that have no free unit.

## 5. How many more fit

Devices of one model placed one after another, first fit, under the same limits (counting stops at 1,000).

| Model | Size | Allocated power | Heat | More that fit | Stopped by |
|---|---|---|---|---|---|
| sw-1u | 1 U | 0.24 kW | 0.15 kW | 87 | power capacity |
| srv-1u | 1 U | 0.28 kW | 0.18 kW | 74 | power capacity |
| srv-2u | 2 U | 0.60 kW | 0.38 kW | 34 | power capacity |
| stor-2u | 2 U | 0.48 kW | 0.32 kW | 43 | power capacity |
| gpu-4u | 4 U | 1.60 kW | 1.10 kW | 13 | power capacity |

## 6. Against what happened next

The simulation ran 72 more months after this date. Months until the limit was reached, forecast against true:

| Resource | True | Forecast | Error | Inside the interval |
|---|---|---|---|---|
| Space | 28 | 16.4 | -11.6 | yes |
| Power | 21 | 9.3 | -11.7 | no |
| Cooling | not within the simulated future | 26.6 | n/a | n/a |

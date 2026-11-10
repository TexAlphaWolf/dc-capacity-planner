# Limitations

- **The data centers are synthetic.** The projects, the device mix, the lifetimes and the plants come from a generator chosen to be
  plausible. The analysis was not run on a real inventory in this repository, and the accuracy figures are those of the generator's
  growth, which is steadier than most real ones.
- **A trend forecast sees only growth.** It cannot know that devices will be retired, that a project is cancelled, or that a limit
  will stop growth before the policy limit is reached. On the synthetic data centers it is early on average, and for 126 of 505 forecasts it
  announces a crossing that does not happen (61 of them within 24 months).
- **The interval is a near-term interval.** The 90% interval holds the true month 87.5% of the time up to a year ahead and 85.4% up to two,
  75.0% at 25 to 48 months and 44.7% beyond. Space is weaker (59.4%) than power and cooling (about 84%). Do not plan a purchase on a
  forecast more than two years away without a second opinion.
- **Growth in steps is not growth in a line.** A migration or a customer adds a step; a 24-month window with one step in it gives a
  slope that is neither the step nor the trend. Choose `--window` and read the rack and series data.
- **Power is allocated from the nameplate, heat from the measured draw.** The nameplate x derate is a planning convention (a UPS is
  sized on what could be drawn), the typical draw is what is measured; both come from the inventory and nothing here measures a rack.
- **Cooling is a plant capacity, not an airflow model.** Hot spots, containment and per-rack cooling are outside it; a data center
  that is fine in total can still have a rack that overheats.
- **Redundancy is a count.** A plant has `units` and `redundant` spares; the usable capacity is the units that remain. No failure
  scenario (N+1 with one unit down, a transfer to a generator) is modelled.
- **First fit is a policy, not the only one.** The "how many more fit" count places devices lowest rack and lowest unit first, with
  no regard for balance between racks or for devices that go in pairs; a different placement policy changes the count (never above the
  limit). Counting stops at 1,000.
- **One device at a time, one unit position.** A device is a block of consecutive units in one rack. Blade chassis, half-width
  devices, zero-U PDUs and cable management are not modelled.
- **Times are medians of a few runs on one computer.** The plain Python implementation's time is measured on a small inventory and
  scaled to each size, so the speed-up column is an extrapolation.

"""Forex forecasting (P13-T05, design section 7, DEC-22): a feature pipeline, baselines,
statistical and machine-learning forecasters, walk-forward evaluation against the baselines,
calibration, drift monitoring and the forecast API.

Model outputs are statistical estimates with stated uncertainty, never promises. Models compute in
`float64` (the libraries require it); prices shown to users are converted to `Decimal` at the
boundary with explicit rounding. Money, pips, lots and position sizes never pass through here.
No language model computes, edits or invents a forecast."""

"""Synthetic-but-documented risk-based-authentication (RBA) dataset generator.

Why synthetic: `dataset/rba-sample.csv` is an explicitly invented 20-row bootstrap sample
(see `dataset/README.md`) and is far too small for a defensible train/test classifier
evaluation. The real public dataset (Wiefling et al., Zenodo 2022,
doi:10.5281/zenodo.6782155) is multi-gigabyte and fetched on demand only
(`npm run dataset:fetch`), not committed here. This generator produces a larger dataset from
an explicit, documented data-generating process (DGP) so that every classifier metric
computed against it is real (actually computed by scikit-learn) even though the underlying
labels are synthetic rather than sourced from the real breach-report dataset.

Data-generating process
------------------------
Each row models one login attempt for a synthetic population of users. Features:

  - country_risk        in [0,1], drawn per-country from a fixed risk table (higher = riskier)
  - asn_reputation_risk  in [0,1], drawn per-ASN from a fixed table (higher = riskier)
  - is_new_country       1 if this is the first time this user's synthetic history shows this country
  - is_new_device        1 if this is the first time this user's synthetic history shows this device type
  - round_trip_time_ms   log-normal, shifted upward for attack traffic (proxy vs. mobile carrier RTT)
  - is_attack_ip         drawn from a small pool of "known-bad" ASNs, independent of label
  - hour_of_day          uniform 0-23; attacks are weighted slightly toward off-hours

Ground-truth label (is_account_takeover) is generated from a logistic model over a weighted
sum of the above features plus independent Gaussian noise, i.e. a classic synthetic
classification benchmark: labels are NOT independently drawn at random, they are a genuine
(if synthetic) function of the features, so a classifier trained on these features has real,
non-trivial signal to learn - but the added noise term keeps the task from being perfectly
separable, which is what keeps reported metrics honest rather than trivially 1.0.

Usage:
    py research/data/generate_rba_dataset.py [--n 6000] [--seed 42] [--out <path>]
"""
from __future__ import annotations

import argparse
import os
import numpy as np
import pandas as pd

COUNTRY_RISK = {
    "United States": 0.05, "United Kingdom": 0.06, "Germany": 0.05, "Canada": 0.05,
    "France": 0.07, "Australia": 0.06, "Japan": 0.05, "Netherlands": 0.08,
    "Nigeria": 0.55, "Vietnam": 0.35, "Brazil": 0.20, "India": 0.18,
    "Russia": 0.60, "Romania": 0.40, "Indonesia": 0.30, "Pakistan": 0.45,
}
DEVICE_TYPES = ["desktop", "mobile", "tablet"]
KNOWN_BAD_ASN_SHARE = 0.12  # fraction of synthetic ASNs treated as "known-bad" reputation


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate(n: int = 6000, seed: int = 42) -> pd.DataFrame:
    rng = _rng(seed)
    countries = list(COUNTRY_RISK.keys())
    country_weights = np.array([1.0 if COUNTRY_RISK[c] < 0.15 else 0.15 for c in countries])
    country_weights /= country_weights.sum()

    country = rng.choice(countries, size=n, p=country_weights)
    country_risk = np.array([COUNTRY_RISK[c] for c in country])

    asn_reputation_risk = rng.beta(1.5, 6.0, size=n)  # right-skewed: most ASNs low-risk
    is_known_bad_asn = (asn_reputation_risk > np.quantile(asn_reputation_risk, 1 - KNOWN_BAD_ASN_SHARE)).astype(int)

    device_type = rng.choice(DEVICE_TYPES, size=n, p=[0.55, 0.35, 0.10])
    is_new_country = rng.binomial(1, 0.08 + 0.5 * country_risk)  # riskier countries -> more likely "new" for this user
    is_new_device = rng.binomial(1, 0.10, size=n)

    base_rtt = rng.lognormal(mean=4.3, sigma=0.35, size=n)  # ~70ms median
    attack_rtt_bump = rng.lognormal(mean=5.0, sigma=0.5, size=n) * is_known_bad_asn
    round_trip_time_ms = base_rtt + attack_rtt_bump

    hour_of_day = rng.integers(0, 24, size=n)
    offhours_weight = np.where((hour_of_day < 6) | (hour_of_day > 22), 1.0, 0.0)

    is_attack_ip = np.clip(
        rng.binomial(1, 0.05 + 0.7 * is_known_bad_asn + 0.05 * is_new_country),
        0, 1,
    )

    # Documented logistic data-generating process for the label.
    z = (
        -3.2
        + 4.0 * country_risk
        + 3.2 * asn_reputation_risk
        + 1.6 * is_new_country
        + 0.9 * is_new_device
        + 2.4 * is_attack_ip
        + 0.4 * offhours_weight
        + 0.6 * np.log1p(round_trip_time_ms / 100.0)
        + rng.normal(0, 1.15, size=n)  # noise term keeps the task non-trivial
    )
    p_ato = 1.0 / (1.0 + np.exp(-z))
    is_account_takeover = rng.binomial(1, p_ato)

    login_successful = np.where(is_account_takeover == 1, rng.binomial(1, 0.6, size=n), rng.binomial(1, 0.97, size=n))

    return pd.DataFrame({
        "country": country,
        "country_risk": country_risk,
        "asn_reputation_risk": asn_reputation_risk,
        "device_type": device_type,
        "is_new_country": is_new_country,
        "is_new_device": is_new_device,
        "round_trip_time_ms": round_trip_time_ms,
        "hour_of_day": hour_of_day,
        "is_attack_ip": is_attack_ip,
        "login_successful": login_successful,
        "is_account_takeover": is_account_takeover,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=6000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default=os.path.join(os.path.dirname(__file__), "generated", "rba_synthetic.csv"))
    args = parser.parse_args()

    df = generate(args.n, args.seed)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} rows to {args.out}")
    print(f"positive rate (is_account_takeover=1): {df['is_account_takeover'].mean():.4f}")

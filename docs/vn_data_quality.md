# Vietnamese Stock Data Quality Report

**Generated:** 2026-09-30T18:11:30.262532+00:00
**Source:** SSI iBoard public API (`iboard-api.ssi.com.vn`)
**Pipeline:** Bronze -> Silver -> Gold (Medallion Architecture)
**Lookback:** 3650 days (~10.0 years)
**Ingestion time:** 955.4s

## Coverage

| Status | Count | % |
|--------|-------|---|
| OK (clean OHLC) | 3 | 5.7% |
| Warnings (minor OHLC range violations) | 47 | 88.7% |
| Failed (no SSI data) | 3 | 5.7% |
| **Total symbols** | **53** | **100%** |

- **Bronze records (raw):** 117,686
- **Silver records (cleaned):** 117,401
- **Gold records (features):** 119,151

## Historical Depth

| Span | Symbols |
|------|---------|
| 10y+ | 36 (VCB, MBB, ACB, BID, CTG, SHB...) |
| 8-10y | 10 (TCB, HDB, TPB, LPB, VHM, VRE...) |
| 5-8y | 4 (STB, MSB, OCB, ITA) |
| <5y | 3 (MBC, PLD, PNVN) |

## Sector Coverage

| Sector | Symbols | Count |
|--------|---------|-------|
| Banks | VCB, TCB, MBB, ACB, BID, CTG, HDB, STB, TPB, MSB, SHB, LPB, EIB, OCB, VIB, NVB | 16 |
| Real estate | VHM, VRE, KDH, VIC, NVL, PDR, BCM, HDG, DIG, FCN, ITA, HCM, NSC, MBC, SBT, IMP, PLD | 17 |
| Technology | FPT, CMG | 2 |
| Consumer / Retail | MWG, PNJ, MSN, SAB, VNM, PNVN | 6 |
| Industrial / Materials | HPG, GAS, PLX, POW, REE, KDC, DHG | 7 |
| Securities | SSI, VND, VCI, SHS | 4 |

## Quality Checks Performed

Each ticker was checked for:

1. **OHLC consistency** — `high >= low`, `low <= open <= high`, `low <= close <= high`
2. **Negative prices** — `open`, `high`, `low`, `close` must be `> 0`
3. **Missing values** — `open`, `close`, `volume` must not be `NaN`
4. **Date gaps** — gap > 7 calendar days flagged (only on weekends/holidays)
5. **Duplicate timestamps** — de-duplicated at write time

Symbols in the **warnings** bucket typically have 1-13 rows where the close price is
equal to the high/low boundary (after price-limit trading). These are valid market
behavior, not data corruption.

## Per-Symbol Detail

| Symbol | Status | Rows | Span | First | Last | Bronze | Silver | Gold |
|--------|--------|-----:|-----:|-------|------|-------:|-------:|-----:|
| VCB | warnings | 2492 | 10.0y | 2016-10-03 | 2026-09-30 | 2492 | 2484 | 2484 |
| TCB | warnings | 2080 | 8.3y | 2018-06-04 | 2026-09-30 | 2080 | 2075 | 2075 |
| MBB | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2483 | 2483 |
| ACB | warnings | 2491 | 10.0y | 2016-10-03 | 2026-09-30 | 2491 | 2489 | 2489 |
| BID | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2491 | 3744 |
| CTG | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2487 | 2487 |
| HDB | warnings | 2176 | 8.7y | 2018-01-05 | 2026-09-30 | 2176 | 2170 | 2170 |
| STB | warnings | 1647 | 6.6y | 2020-02-26 | 2026-09-30 | 1647 | 1646 | 1646 |
| TPB | warnings | 2107 | 8.4y | 2018-04-19 | 2026-09-30 | 2107 | 2096 | 2096 |
| MSB | warnings | 1439 | 5.8y | 2020-12-23 | 2026-09-30 | 1439 | 1435 | 1435 |
| SHB | ok | 2493 | 10.0y | 2016-10-03 | 2026-09-30 | 2493 | 2493 | 2493 |
| LPB | warnings | 2232 | 9.0y | 2017-10-05 | 2026-09-30 | 2232 | 2229 | 2229 |
| EIB | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2490 | 2490 |
| OCB | warnings | 1411 | 5.7y | 2021-01-28 | 2026-09-30 | 1411 | 1410 | 1410 |
| VIB | warnings | 2416 | 9.7y | 2017-01-09 | 2026-09-30 | 2416 | 2415 | 2415 |
| NVB | ok | 2452 | 10.0y | 2016-10-03 | 2026-09-30 | 2452 | 2452 | 2452 |
| VHM | warnings | 2088 | 8.4y | 2018-05-17 | 2026-09-30 | 2088 | 2087 | 2087 |
| VRE | warnings | 2215 | 8.9y | 2017-11-06 | 2026-09-30 | 2215 | 2207 | 2207 |
| KDH | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2490 | 2490 |
| VIC | warnings | 2492 | 10.0y | 2016-10-03 | 2026-09-30 | 2492 | 2481 | 2481 |
| NVL | warnings | 2432 | 9.8y | 2016-12-28 | 2026-09-30 | 2432 | 2426 | 2426 |
| PDR | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2488 | 2488 |
| BCM | warnings | 2127 | 8.6y | 2018-02-21 | 2026-09-30 | 2127 | 2125 | 2125 |
| HDG | warnings | 2493 | 10.0y | 2016-10-03 | 2026-09-30 | 2493 | 2485 | 2485 |
| DIG | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2485 | 2485 |
| FCN | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2491 | 2491 |
| ITA | warnings | 1994 | 8.0y | 2016-10-03 | 2024-09-25 | 1994 | 1989 | 2486 |
| HCM | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2489 | 2489 |
| NSC | warnings | 2362 | 10.0y | 2016-10-03 | 2026-09-30 | 2362 | 2358 | 2358 |
| MBC | fetch_failed | 0 | 0.0y | - | - | None | None | None |
| SBT | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2483 | 2483 |
| IMP | warnings | 2478 | 10.0y | 2016-10-03 | 2026-09-30 | 2478 | 2470 | 2470 |
| PLD | fetch_failed | 0 | 0.0y | - | - | None | None | None |
| FPT | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2489 | 2489 |
| CMG | warnings | 2487 | 10.0y | 2016-10-03 | 2026-09-30 | 2487 | 2475 | 2475 |
| MWG | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2484 | 2484 |
| PNJ | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2487 | 2487 |
| MSN | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2485 | 2485 |
| SAB | warnings | 2448 | 9.8y | 2016-12-06 | 2026-09-30 | 2448 | 2437 | 2437 |
| VNM | warnings | 2492 | 10.0y | 2016-10-03 | 2026-09-30 | 2492 | 2484 | 2484 |
| PNVN | fetch_failed | 0 | 0.0y | - | - | None | None | None |
| HPG | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2491 | 2491 |
| GAS | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2490 | 2490 |
| PLX | warnings | 2357 | 9.4y | 2017-04-21 | 2026-09-30 | 2357 | 2354 | 2354 |
| POW | warnings | 2131 | 8.6y | 2018-03-06 | 2026-09-30 | 2131 | 2128 | 2128 |
| REE | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2479 | 2479 |
| KDC | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2489 | 2489 |
| DHG | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2490 | 2490 |
| SSI | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2488 | 2488 |
| VND | warnings | 2482 | 10.0y | 2016-10-03 | 2026-09-30 | 2482 | 2476 | 2476 |
| VCI | warnings | 2302 | 9.2y | 2017-07-07 | 2026-09-30 | 2302 | 2291 | 2291 |
| HCM | warnings | 2494 | 10.0y | 2016-10-03 | 2026-09-30 | 2494 | 2489 | 2489 |
| SHS | ok | 2496 | 10.0y | 2016-10-03 | 2026-09-30 | 2496 | 2496 | 2496 |

## Failed Symbols

| Symbol | Reason |
|--------|--------|
| MBC | no data on SSI |
| PLD | no data on SSI |
| PNVN | no data on SSI |

## Source Endpoint

```
GET https://iboard-api.ssi.com.vn/statistics/charts/history
    ?symbol={TICKER}
    &resolution=1D
    &from={unix_start}
    &to={unix_end}
```

Response:

```json
{
  "code": "SUCCESS",
  "data": {
    "t": [unix_seconds, ...],  // bar timestamps
    "o": [...], "h": [...], "l": [...], "c": [...],
    "v": [...],                  // matched volume
    "s": "ok"
  }
}
```

SSI returns prices in *thousands* of VND. `SSIVNProvider._normalize()` multiplies
`open/high/low/close` by 1,000 so the lakehouse stores absolute VND.

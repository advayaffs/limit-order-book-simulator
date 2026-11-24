# Limit Order Book & Market Making Simulator

A price-time-priority matching engine and a controlled comparison of two quoting policies.

## Overview

This experiment asks how inventory-aware quoting changes turnover, marked P&L and drawdown under identical synthetic market order flow. The matching engine and market maker are implemented in one Python file.

## Method

- Maintain a queue of orders at each price level. Execute against the best opposing price, then FIFO within that price; support partial fills and cancellation.
- Retain queue priority when an unchanged quote is left resting. A competing dealer provides liquidity.
- Compare symmetric quotes with quotes shifted according to the maker's inventory. Both policies have a 20-share position limit.
- Generate identical seeded incoming flow in two separate books, including orders correlated with the upcoming reference-price move.
- Mark inventory at the simulated reference price, subtract per-share fees and track drawdown.

## Run

```bash
python market_maker.py
python market_maker.py --steps 5000 --seed 7 --csv session.csv
python market_maker.py --steps 20000 --seed 17 --fee 0.1
```

Prices are integer cents. The `--fee` flag is in cents per maker share filled, not dollars.

## Reproduced results

5,000 incoming orders, seed 7, fee 0.1 cents per share.

| Strategy | Shares filled | End position | Peak absolute position | Net marked P&L | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Symmetric | 10,465 | −7 | 20 | $57.28 | $1.95 |
| Inventory-aware | 13,890 | −4 | 20 | $51.38 | $0.97 |

Inventory-aware quoting reduced drawdown in this run but also reduced marked P&L. It did not dominate on every metric. The event-level CSV is included for further analysis.

## Limitations and next steps

The synthetic flow and dealer are stylized; this is not an exchange replay. Latency, real queue estimates, market impact and liquidation costs are not fully modeled. Next steps include replaying recorded depth events and comparing distributions over many independent seeds.

## Requirements and files

Python 3.10+; no third-party dependencies are required.

- `market_maker.py` — original project implementation.
- `requirements.txt` — dependency notes.
- `results/` — outputs from the example run, including [terminal output](results/example_run.txt).

The example was rerun using the bundled source. This is a research/educational project; it is not a production system.

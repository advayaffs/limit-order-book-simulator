"""A small exchange and two market makers. Run with Python 3.10 or later.

    python market_maker.py
    python market_maker.py --seed 17 --steps 20000 --csv session.csv

Prices are integer cents. One step is one incoming market order, of which
any unfilled quantity expires. The two strategies see the same incoming flow
in separate books. Each CSV row records equity after that step.
"""

import argparse
import csv
import random
from collections import deque
from dataclasses import dataclass


@dataclass(eq=False)
class Order:
    owner: str
    side: str
    price: int
    remaining: int


class Book:
    def __init__(self):
        self.levels = {"buy": {}, "sell": {}}

    def best(self, side):
        prices = self.levels[side]
        return max(prices, default=None) if side == "buy" else min(prices, default=None)

    def cancel(self, order):
        levels = self.levels[order.side]
        queue = levels[order.price]
        queue.remove(order)
        if not queue:
            del levels[order.price]

    def submit(self, owner, side, size, limit=None):
        """Return the resting remainder (if any) and (resting order, fill size) pairs."""
        if side not in self.levels or size <= 0:
            raise ValueError("Expected buy or sell and a positive size")
        opposite = "sell" if side == "buy" else "buy"
        fills = []
        while size and (price := self.best(opposite)) is not None:
            if limit is not None:
                if (side == "buy" and price > limit) or (side == "sell" and price < limit):
                    break
            queue = self.levels[opposite][price]
            first = queue[0]
            traded = min(size, first.remaining)
            fills.append((first, traded))
            size -= traded
            first.remaining -= traded
            if first.remaining == 0:
                queue.popleft()
            if not queue:
                del self.levels[opposite][price]

        resting = None
        if limit is not None and size:
            resting = Order(owner, side, limit, size)
            self.levels[side].setdefault(limit, deque()).append(resting)
        return resting, fills


@dataclass
class Account:
    position: int = 0
    cash_cents: int = 0
    volume: int = 0
    peak_inventory: int = 0
    peak_equity: float = 0
    drawdown: float = 0

    def fill(self, side, price, size):
        signed_size = size if side == "buy" else -size
        self.position += signed_size
        self.cash_cents -= signed_size * price
        self.volume += size
        self.peak_inventory = max(self.peak_inventory, abs(self.position))

    def mark(self, reference, fee):
        equity = self.cash_cents + self.position * reference - self.volume * fee
        self.peak_equity = max(self.peak_equity, equity)
        self.drawdown = max(self.drawdown, self.peak_equity - equity)
        return equity


def update_quotes(book, orders, owner, targets):
    """An unchanged quote keeps its place, including after a partial fill."""
    for side, old in list(orders.items()):
        price, capacity = targets[side]
        if old.remaining and old.price == price and old.remaining <= capacity:
            continue
        if old.remaining:
            book.cancel(old)
        del orders[side]

    fills = []
    for side, (price, size) in targets.items():
        if size and side not in orders:
            order, trades = book.submit(owner, side, size, price)
            fills.extend(trades)
            if order:
                orders[side] = order
    return fills


def market_flow(steps, seed):
    rng = random.Random(seed)
    reference = 10000
    for _ in range(steps):
        move = rng.choices((-2, -1, 0, 1, 2), (1, 5, 28, 5, 1))[0]
        new_reference = max(100, reference + move)
        # Some traders react to news before the market maker can reprice.
        buy = rng.random() < 0.5
        if move and rng.random() < 0.75:
            buy = move > 0
        yield reference, new_reference, "buy" if buy else "sell", rng.randint(1, 18)
        reference = new_reference


LOT = 5
POSITION_LIMIT = 20


def run(strategy, steps, seed, fee, writer=None):
    book = Book()
    account = Account()
    maker_orders = {}
    dealer_orders = {}
    equity = 0
    for step, (public, new_mark, side, size) in enumerate(market_flow(steps, seed), 1):
        # A competing dealer supplies ten shares one tick either side of the
        # public reference. Its reprices may execute against our stale quotes.
        dealer = {"buy": (public - 1, 10), "sell": (public + 1, 10)}
        start_position = account.position
        start_volume = account.volume
        dealer_trades = update_quotes(book, dealer_orders, "dealer", dealer)

        for order, filled in dealer_trades:
            account.fill(order.side, order.price, filled)

        # At five shares long we step the bid back one tick and lower the ask.
        # Clip at the opposite touch to keep our quotes passive.
        skew = int(account.position / LOT) if strategy == "inventory" else 0
        bid = public - 1 - skew
        ask = public + 1 - skew
        # The competing dealer's limits bound passive prices even if depleted.
        bid = min(bid, public)
        ask = max(ask, public)
        targets = {
            "buy": (bid, min(LOT, POSITION_LIMIT - account.position)),
            "sell": (ask, min(LOT, POSITION_LIMIT + account.position)),
        }
        maker_trades = update_quotes(book, maker_orders, "maker", targets)
        if maker_trades:
            raise RuntimeError("A passive maker quote crossed the book")
        _, trades = book.submit("trader", side, size)
        for order, filled in trades:
            if order.owner == "maker":
                account.fill(order.side, order.price, filled)
        equity = account.mark(new_mark, fee)
        if writer:
            volume = account.volume - start_volume
            bought = (volume + account.position - start_position) // 2
            sold = volume - bought
            writer.writerow([strategy, step, new_mark, side, size, bought, sold,
                             account.position, account.cash_cents, round(equity / 100, 5)])
    return account, equity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--fee", type=float, default=0.1, help="cents per maker share filled")
    parser.add_argument("--csv", metavar="PATH", help="save a row per event and strategy")
    args = parser.parse_args()
    if args.steps < 1 or not 0 <= args.fee < float("inf"):
        parser.error("use positive steps and a finite nonnegative fee")

    print(f"Synthetic session | {args.steps:,} orders | seed {args.seed} | fee {args.fee:g} cents/share")
    print(f"{'Strategy':12} {'Shares':>8} {'End pos':>8} {'Peak |pos|':>11} {'Net P&L $':>11} {'Max DD $':>10}")
    output = open(args.csv, "w", newline="", encoding="utf-8") if args.csv else None
    try:
        writer = csv.writer(output) if output else None
        if writer:
            writer.writerow(["strategy", "step", "reference_cents", "incoming_side", "incoming_size",
                             "maker_bought", "maker_sold", "position", "cash_before_fees_cents", "net_equity_usd"])
        for strategy in ("symmetric", "inventory"):
            account, equity = run(strategy, args.steps, args.seed, args.fee, writer)
            print(f"{strategy:12} {account.volume:8} {account.position:8} {account.peak_inventory:11}"
                  f" {equity / 100:11.2f} {account.drawdown / 100:10.2f}")
    finally:
        if output:
            output.close()


if __name__ == "__main__":
    main()

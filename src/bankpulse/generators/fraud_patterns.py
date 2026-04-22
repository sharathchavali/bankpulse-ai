"""
Fraud pattern injectors.

Each injector takes a victim customer + card + merchant pool, and produces a
sequence of fraudulent transactions consistent with a real-world fraud typology.
Ground-truth labels are attached so later ML / rule-based scoring can be
evaluated properly.

The six patterns modelled here are based on how real fraud ops teams
actually categorise cases (card present vs CNP, first-party vs third-party).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from random import Random
from uuid import UUID, uuid4

from bankpulse.models import (
    Channel,
    FraudPattern,
    Merchant,
    Transaction,
    TransactionStatus,
)


class FraudInjector:
    """Produces sequences of fraudulent transactions on a victim account."""

    def __init__(self, seed: int = 77) -> None:
        self._rand = Random(seed)

    # ---- helpers ---------------------------------------------------------

    def _pick_merchant(
        self, merchants: list[Merchant], *, online: bool | None = None
    ) -> Merchant:
        pool = merchants
        if online is True:
            pool = [m for m in merchants if m.is_online] or merchants
        elif online is False:
            pool = [m for m in merchants if not m.is_online] or merchants
        return self._rand.choice(pool)

    def _base_txn(
        self,
        *,
        customer_id: UUID,
        card_id: UUID,
        merchant: Merchant,
        ts: datetime,
        amount: Decimal,
        channel: Channel,
        status: TransactionStatus,
        pattern: FraudPattern,
        location_city: str,
        location_country: str,
    ) -> Transaction:
        return Transaction(
            transaction_id=uuid4(),
            customer_id=customer_id,
            card_id=card_id,
            merchant_id=merchant.merchant_id,
            transaction_ts=ts,
            amount_eur=amount,
            channel=channel,
            status=status,
            location_city=location_city,
            location_country=location_country,
            is_fraud=True,
            fraud_pattern=pattern,
        )

    # ---- patterns --------------------------------------------------------

    def inject_card_testing(
        self, customer_id: UUID, card_id: UUID,
        merchants: list[Merchant], start_ts: datetime,
    ) -> list[Transaction]:
        """Many tiny authorisations in quick succession — testing stolen card numbers."""
        count = self._rand.randint(6, 15)
        out: list[Transaction] = []
        for i in range(count):
            m = self._pick_merchant(merchants, online=True)
            out.append(self._base_txn(
                customer_id=customer_id, card_id=card_id, merchant=m,
                ts=start_ts + timedelta(seconds=i * self._rand.randint(5, 45)),
                amount=Decimal(f"{self._rand.uniform(0.5, 4.99):.2f}"),
                channel=Channel.ECOMMERCE,
                status=TransactionStatus.DECLINED if i < count - 2 else TransactionStatus.APPROVED,
                pattern=FraudPattern.CARD_TESTING,
                location_city=m.city, location_country=m.country,
            ))
        return out

    def inject_account_takeover(
        self, customer_id: UUID, card_id: UUID,
        merchants: list[Merchant], start_ts: datetime,
    ) -> list[Transaction]:
        """Few high-value CNP purchases after credential compromise."""
        count = self._rand.randint(2, 5)
        out: list[Transaction] = []
        for i in range(count):
            m = self._pick_merchant(merchants, online=True)
            out.append(self._base_txn(
                customer_id=customer_id, card_id=card_id, merchant=m,
                ts=start_ts + timedelta(minutes=i * self._rand.randint(5, 30)),
                amount=Decimal(f"{self._rand.uniform(250, 2500):.2f}"),
                channel=Channel.ECOMMERCE,
                status=TransactionStatus.APPROVED,
                pattern=FraudPattern.ACCOUNT_TAKEOVER,
                location_city=m.city, location_country=m.country,
            ))
        return out

    def inject_velocity_attack(
        self, customer_id: UUID, card_id: UUID,
        merchants: list[Merchant], start_ts: datetime,
    ) -> list[Transaction]:
        """Burst of card-present swipes within minutes at one merchant."""
        count = self._rand.randint(4, 8)
        m = self._pick_merchant(merchants, online=False)
        out: list[Transaction] = []
        for i in range(count):
            out.append(self._base_txn(
                customer_id=customer_id, card_id=card_id, merchant=m,
                ts=start_ts + timedelta(minutes=i * self._rand.randint(1, 4)),
                amount=Decimal(f"{self._rand.uniform(40, 300):.2f}"),
                channel=Channel.CARD_PRESENT,
                status=TransactionStatus.APPROVED,
                pattern=FraudPattern.VELOCITY_ATTACK,
                location_city=m.city, location_country=m.country,
            ))
        return out

    def inject_impossible_travel(
        self, customer_id: UUID, card_id: UUID,
        merchants: list[Merchant], start_ts: datetime,
    ) -> list[Transaction]:
        """Two card-present txns too far apart geographically to be real."""
        m1 = self._pick_merchant(merchants, online=False)
        other_country_pool = [
            m for m in merchants if m.country != m1.country and not m.is_online
        ]
        m2 = self._rand.choice(other_country_pool) if other_country_pool else m1
        return [
            self._base_txn(
                customer_id=customer_id, card_id=card_id, merchant=m1,
                ts=start_ts,
                amount=Decimal(f"{self._rand.uniform(20, 150):.2f}"),
                channel=Channel.CARD_PRESENT,
                status=TransactionStatus.APPROVED,
                pattern=FraudPattern.IMPOSSIBLE_TRAVEL,
                location_city=m1.city, location_country=m1.country,
            ),
            self._base_txn(
                customer_id=customer_id, card_id=card_id, merchant=m2,
                ts=start_ts + timedelta(minutes=self._rand.randint(30, 90)),
                amount=Decimal(f"{self._rand.uniform(20, 150):.2f}"),
                channel=Channel.CARD_PRESENT,
                status=TransactionStatus.APPROVED,
                pattern=FraudPattern.IMPOSSIBLE_TRAVEL,
                location_city=m2.city, location_country=m2.country,
            ),
        ]

    def inject_synthetic_identity(
        self, customer_id: UUID, card_id: UUID,
        merchants: list[Merchant], start_ts: datetime,
    ) -> list[Transaction]:
        """Bust-out: small spend building reputation, then 1–2 large hits."""
        out: list[Transaction] = []
        for i in range(self._rand.randint(3, 6)):
            m = self._pick_merchant(merchants)
            out.append(self._base_txn(
                customer_id=customer_id, card_id=card_id, merchant=m,
                ts=start_ts + timedelta(hours=i * self._rand.randint(6, 48)),
                amount=Decimal(f"{self._rand.uniform(10, 80):.2f}"),
                channel=self._rand.choice([Channel.ECOMMERCE, Channel.CARD_PRESENT]),
                status=TransactionStatus.APPROVED,
                pattern=FraudPattern.SYNTHETIC_IDENTITY,
                location_city=m.city, location_country=m.country,
            ))
        # The bust-out
        m = self._pick_merchant(merchants, online=True)
        out.append(self._base_txn(
            customer_id=customer_id, card_id=card_id, merchant=m,
            ts=start_ts + timedelta(days=self._rand.randint(3, 10)),
            amount=Decimal(f"{self._rand.uniform(3000, 9000):.2f}"),
            channel=Channel.ECOMMERCE,
            status=TransactionStatus.APPROVED,
            pattern=FraudPattern.SYNTHETIC_IDENTITY,
            location_city=m.city, location_country=m.country,
        ))
        return out

    def inject_merchant_collusion(
        self, customer_id: UUID, card_id: UUID,
        merchants: list[Merchant], start_ts: datetime,
    ) -> list[Transaction]:
        """Flagged merchant, rounded amounts, repeat business."""
        risky = [m for m in merchants if m.risk_flag]
        if not risky:
            return []
        m = self._rand.choice(risky)
        out: list[Transaction] = []
        for i in range(self._rand.randint(2, 4)):
            amount = Decimal(self._rand.choice([100, 200, 500, 750, 1000]))
            out.append(self._base_txn(
                customer_id=customer_id, card_id=card_id, merchant=m,
                ts=start_ts + timedelta(hours=i * 12),
                amount=amount,
                channel=Channel.ECOMMERCE,
                status=TransactionStatus.APPROVED,
                pattern=FraudPattern.MERCHANT_COLLUSION,
                location_city=m.city, location_country=m.country,
            ))
        return out

    # ---- dispatcher ------------------------------------------------------

    _PATTERN_WEIGHTS: tuple[tuple[FraudPattern, float], ...] = (
        (FraudPattern.CARD_TESTING,       0.30),
        (FraudPattern.ACCOUNT_TAKEOVER,   0.25),
        (FraudPattern.VELOCITY_ATTACK,    0.15),
        (FraudPattern.IMPOSSIBLE_TRAVEL,  0.10),
        (FraudPattern.SYNTHETIC_IDENTITY, 0.15),
        (FraudPattern.MERCHANT_COLLUSION, 0.05),
    )

    def inject_random(
        self, customer_id: UUID, card_id: UUID,
        merchants: list[Merchant], start_ts: datetime,
    ) -> list[Transaction]:
        pattern = self._rand.choices(
            [p for p, _ in self._PATTERN_WEIGHTS],
            weights=[w for _, w in self._PATTERN_WEIGHTS], k=1,
        )[0]
        dispatch = {
            FraudPattern.CARD_TESTING:       self.inject_card_testing,
            FraudPattern.ACCOUNT_TAKEOVER:   self.inject_account_takeover,
            FraudPattern.VELOCITY_ATTACK:    self.inject_velocity_attack,
            FraudPattern.IMPOSSIBLE_TRAVEL:  self.inject_impossible_travel,
            FraudPattern.SYNTHETIC_IDENTITY: self.inject_synthetic_identity,
            FraudPattern.MERCHANT_COLLUSION: self.inject_merchant_collusion,
        }
        return dispatch[pattern](customer_id, card_id, merchants, start_ts)
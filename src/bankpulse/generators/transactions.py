"""Transaction generator. Produces realistic legit + fraud mix."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from random import Random
from uuid import UUID, uuid4

import numpy as np

from bankpulse.generators.fraud_patterns import FraudInjector
from bankpulse.models import (
    Card,
    CardNetwork,
    Channel,
    Customer,
    FraudPattern,
    Merchant,
    Transaction,
    TransactionStatus,
)


class TransactionGenerator:
    """
    Generates transactions for a population of customers over a date window.

    Each customer gets:
      * 1–2 cards
      * Daily transaction count ~ Poisson(λ) where λ depends on income
      * Amount ~ log-normal, with tails
      * Geography: mostly home country, occasional travel
      * Timing: trimodal — commute, lunch, evening peaks
    """

    def __init__(self, seed: int = 99, fraud_rate: float = 0.008) -> None:
        self._rand = Random(seed)
        self._np = np.random.default_rng(seed)
        self._fraud_rate = fraud_rate
        self._fraud = FraudInjector(seed=seed + 1)

    # ---- cards -----------------------------------------------------------

    def generate_cards(self, customers: list[Customer]) -> list[Card]:
        out: list[Card] = []
        for c in customers:
            for _ in range(self._rand.randint(1, 2)):
                issued = c.signup_date + timedelta(days=self._rand.randint(0, 90))
                out.append(Card(
                    card_id=uuid4(),
                    customer_id=c.customer_id,
                    card_network=self._rand.choice(list(CardNetwork)),
                    issued_date=issued,
                    expiry_date=issued + timedelta(days=4 * 365),
                    is_active=True,
                ))
        return out

    # ---- legit txns ------------------------------------------------------

    def _poisson_daily_count(self, customer: Customer) -> int:
        # Base rate + income skew
        base = 1.8
        income_factor = float(customer.annual_income_eur) / 60_000.0
        lam = max(0.3, base * min(3.0, income_factor))
        return int(self._np.poisson(lam))

    def _random_time_on(self, day: datetime) -> datetime:
        # Trimodal: morning commute, lunch, evening
        hour_choices = list(range(24))
        hour_weights = [
            0.5, 0.3, 0.3, 0.3, 0.4, 0.6, 1.0, 1.4, 1.6, 1.4, 1.2, 1.6,
            1.8, 1.7, 1.4, 1.3, 1.4, 1.8, 2.2, 2.5, 2.3, 1.8, 1.2, 0.8,
        ]
        h = self._rand.choices(hour_choices, weights=hour_weights, k=1)[0]
        return day.replace(
            hour=h,
            minute=self._rand.randint(0, 59),
            second=self._rand.randint(0, 59),
        )

    def _sample_amount(self) -> Decimal:
        value = float(self._np.lognormal(mean=3.0, sigma=1.1))
        return Decimal(f"{min(value, 5000.0):.2f}")

    def _legit_txn(
        self,
        customer: Customer,
        card: Card,
        merchant: Merchant,
        ts: datetime,
    ) -> Transaction:
        # Most spend is in home country; occasional online/international
        in_home = self._rand.random() < 0.88
        if in_home:
            city, country = customer.home_city, customer.home_country
        else:
            city, country = merchant.city, merchant.country

        # Channel distribution
        if merchant.is_online:
            channel = Channel.ECOMMERCE
        else:
            channel = self._rand.choices(
                [Channel.CARD_PRESENT, Channel.CONTACTLESS, Channel.ATM],
                weights=[0.35, 0.55, 0.10], k=1,
            )[0]

        # 97% approved
        status = (
            TransactionStatus.APPROVED
            if self._rand.random() < 0.97
            else TransactionStatus.DECLINED
        )

        return Transaction(
            transaction_id=uuid4(),
            customer_id=customer.customer_id,
            card_id=card.card_id,
            merchant_id=merchant.merchant_id,
            transaction_ts=ts,
            amount_eur=self._sample_amount(),
            channel=channel,
            status=status,
            location_city=city,
            location_country=country,
            is_fraud=False,
            fraud_pattern=FraudPattern.NONE,
        )

    # ---- top-level -------------------------------------------------------

    def generate(
        self,
        customers: list[Customer],
        cards: list[Card],
        merchants: list[Merchant],
        start_date: datetime,
        days: int,
    ) -> list[Transaction]:
        cards_by_customer: dict[UUID, list[Card]] = {}
        for card in cards:
            cards_by_customer.setdefault(card.customer_id, []).append(card)

        # Sample ~fraud_rate of customers to become victims at some point
        n_victims = max(1, int(len(customers) * self._fraud_rate))
        victims = self._rand.sample(customers, min(n_victims, len(customers)))

        out: list[Transaction] = []

        for day_offset in range(days):
            day = start_date + timedelta(days=day_offset)

            # Legit transactions
            for customer in customers:
                customer_cards = cards_by_customer.get(customer.customer_id, [])
                if not customer_cards:
                    continue

                count = self._poisson_daily_count(customer)
                for _ in range(count):
                    card = self._rand.choice(customer_cards)
                    merchant = self._rand.choice(merchants)
                    ts = self._random_time_on(day)
                    out.append(self._legit_txn(customer, card, merchant, ts))

            # Fraud episodes — roughly daily_fraud_cases per day
            daily_fraud_cases = max(1, n_victims // max(days, 1))
            for _ in range(daily_fraud_cases):
                victim = self._rand.choice(victims)
                cards_v = cards_by_customer.get(victim.customer_id, [])
                if not cards_v:
                    continue
                card = self._rand.choice(cards_v)
                attack_ts = day.replace(
                    hour=self._rand.randint(0, 23),
                    minute=self._rand.randint(0, 59),
                )
                out.extend(self._fraud.inject_random(
                    victim.customer_id, card.card_id, merchants, attack_ts,
                ))

        return out
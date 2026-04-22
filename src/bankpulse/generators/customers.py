"""Synthetic customer generator."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from random import Random
from uuid import uuid4

import numpy as np
from faker import Faker

from bankpulse.models import Customer


# Irish-skewed distribution — most customers in Ireland/UK/EU, some international
_COUNTRY_WEIGHTS: dict[str, float] = {
    "IE": 0.55, "GB": 0.15, "FR": 0.05, "DE": 0.05, "ES": 0.04,
    "IT": 0.03, "NL": 0.03, "PL": 0.03, "US": 0.03, "PT": 0.02, "BE": 0.02,
}
_IRISH_CITIES = [
    "Dublin", "Cork", "Galway", "Limerick", "Waterford", "Drogheda",
    "Dundalk", "Swords", "Bray", "Navan",
]


class CustomerGenerator:
    """Deterministic customer generator. Same seed ⇒ same attributes."""

    def __init__(self, seed: int = 42) -> None:
        self._rand = Random(seed)
        self._np = np.random.default_rng(seed)
        self._faker = Faker(["en_IE", "en_GB", "en_US"])
        self._faker.seed_instance(seed)

    def _pick_country(self) -> str:
        countries = list(_COUNTRY_WEIGHTS.keys())
        weights = list(_COUNTRY_WEIGHTS.values())
        return self._rand.choices(countries, weights=weights, k=1)[0]

    def _pick_city(self, country: str) -> str:
        if country == "IE":
            return self._rand.choice(_IRISH_CITIES)
        return self._faker.city()

    def _sample_income(self) -> Decimal:
        # Log-normal: realistic heavy-tailed income distribution
        value = float(self._np.lognormal(mean=10.6, sigma=0.55))
        return Decimal(f"{value:.2f}")

    def _sample_risk_segment(self) -> str:
        # 70% LOW, 25% MEDIUM, 5% HIGH
        return self._rand.choices(
            ["LOW", "MEDIUM", "HIGH"], weights=[0.70, 0.25, 0.05], k=1
        )[0]

    def generate_one(self) -> Customer:
        country = self._pick_country()
        today = date(2026, 1, 1)
        dob = today - timedelta(days=self._rand.randint(18 * 365, 75 * 365))
        signup = today - timedelta(days=self._rand.randint(30, 10 * 365))
        first = self._faker.first_name()
        last = self._faker.last_name()
        email = f"{first}.{last}.{self._rand.randint(1, 9999)}@example.com".lower()

        return Customer(
            customer_id=uuid4(),
            first_name=first,
            last_name=last,
            email=email,
            date_of_birth=dob,
            home_city=self._pick_city(country),
            home_country=country,
            signup_date=signup,
            risk_segment=self._sample_risk_segment(),
            annual_income_eur=self._sample_income(),
        )

    def generate(self, n: int) -> list[Customer]:
        return [self.generate_one() for _ in range(n)]
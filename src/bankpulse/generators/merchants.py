"""Synthetic merchant generator with realistic MCC categories."""
from __future__ import annotations

from random import Random
from uuid import uuid4

from faker import Faker

from bankpulse.models import Merchant


# Real MCC codes — subset covering common consumer spend categories
_MCC_CATALOG: list[tuple[int, str, bool]] = [
    # (mcc, description, typically_online)
    (5411, "Grocery Stores & Supermarkets", False),
    (5812, "Eating Places & Restaurants", False),
    (5814, "Fast Food Restaurants", False),
    (5541, "Service Stations (Fuel)", False),
    (5912, "Drug Stores & Pharmacies", False),
    (5311, "Department Stores", False),
    (5651, "Family Clothing Stores", False),
    (5732, "Electronics Stores", False),
    (5999, "Miscellaneous Retail", False),
    (4121, "Taxicabs & Limousines", False),
    (4111, "Local & Suburban Transport", False),
    (4511, "Airlines", True),
    (7011, "Hotels, Motels, Resorts", True),
    (5967, "Direct Marketing – Inbound Telemarketing", True),
    (5968, "Direct Marketing – Subscription", True),
    (7995, "Betting & Gaming", True),
    (6011, "Automated Cash Disbursement (ATM)", False),
    (6051, "Non-Financial Institutions – Crypto", True),
]

_COUNTRY_WEIGHTS: dict[str, float] = {
    "IE": 0.45, "GB": 0.15, "FR": 0.05, "DE": 0.05, "ES": 0.05,
    "IT": 0.03, "NL": 0.03, "PL": 0.02, "US": 0.12, "PT": 0.02, "BE": 0.03,
}


class MerchantGenerator:
    def __init__(self, seed: int = 43) -> None:
        self._rand = Random(seed)
        self._faker = Faker()
        self._faker.seed_instance(seed)

    def _pick_country(self) -> str:
        return self._rand.choices(
            list(_COUNTRY_WEIGHTS), weights=list(_COUNTRY_WEIGHTS.values()), k=1
        )[0]

    def generate_one(self) -> Merchant:
        mcc, desc, is_online_default = self._rand.choice(_MCC_CATALOG)
        is_online = is_online_default or self._rand.random() < 0.15
        country = self._pick_country()

        # Merchants in high-risk MCCs (crypto, gambling) are more likely shady
        risk_flag = (
            (mcc in (6051, 7995) and self._rand.random() < 0.25)
            or self._rand.random() < 0.01
        )

        return Merchant(
            merchant_id=uuid4(),
            merchant_name=self._faker.company(),
            mcc=mcc,
            mcc_description=desc,
            city=self._faker.city(),
            country=country,
            is_online=is_online,
            risk_flag=risk_flag,
        )

    def generate(self, n: int) -> list[Merchant]:
        return [self.generate_one() for _ in range(n)]
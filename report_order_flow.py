"""Run one checkout-to-fulfillment metrics handoff."""

import json
from dataclasses import asdict

from commerce_metrics import Checkout, CommerceMetricService, Fulfillment, InfraiMetrics


def main() -> None:
    service = CommerceMetricService(InfraiMetrics())
    checkout = Checkout(
        order_id="ord-2048",
        customer_id="cus-73",
        channel="web",
        total_cents=12900,
    )
    service.record_checkout(checkout)
    update = service.record_fulfillment(
        checkout,
        Fulfillment(
            order_id="ord-2048",
            warehouse="sha-01",
            duration_ms=184000,
            receipt_issued=True,
            customer_notified=True,
        ),
    )
    print(json.dumps(asdict(update), indent=2))


if __name__ == "__main__":
    main()

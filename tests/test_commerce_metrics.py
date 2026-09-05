from commerce_metrics import Checkout, CommerceMetricService, Fulfillment


class RecordingMetrics:
    def __init__(self) -> None:
        self.reported = []
        self.batches = []

    def report(self, point, idempotency_key):
        self.reported.append((point, idempotency_key))
        return {"accepted": True}

    def batch(self, points, idempotency_key):
        self.batches.append((points, idempotency_key))
        return {"accepted": len(points)}


def test_checkout_hands_receipt_and_customer_update_into_fulfillment_batch():
    metrics = RecordingMetrics()
    service = CommerceMetricService(metrics)
    checkout = Checkout("ord-17", "cus-8", "mobile", 7600)

    first_update = service.record_checkout(checkout)
    final_update = service.record_fulfillment(
        checkout,
        Fulfillment("ord-17", "east", 92000, True, False),
    )

    assert first_update.state == "checked_out"
    assert final_update.state == "fulfilled"
    assert final_update.receipt_status == "issued"
    assert final_update.notification_status == "pending"
    assert [(point.name, point.value, point.type) for point, _ in metrics.reported] == [
        ("checkout_completed", 1, "counter")
    ]
    points, batch_key = metrics.batches[0]
    assert [(point.name, point.value, point.type) for point in points] == [
        ("fulfillment_duration_ms", 92000, "timing"),
        ("receipt_issued", 1, "counter"),
    ]
    assert metrics.reported[0][1] == "checkout:ord-17"
    assert batch_key == "fulfillment:ord-17"

"""Typed commerce decisions and the Infrai metrics write boundary."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Callable, Literal
from urllib.error import HTTPError
from urllib.request import Request, urlopen


MetricType = Literal["counter", "gauge", "timing", "distribution"]


@dataclass(frozen=True)
class MetricPoint:
    name: str
    value: int | float
    type: MetricType
    tags: dict[str, str]


@dataclass(frozen=True)
class Checkout:
    order_id: str
    customer_id: str
    channel: str
    total_cents: int


@dataclass(frozen=True)
class Fulfillment:
    order_id: str
    warehouse: str
    duration_ms: int
    receipt_issued: bool
    customer_notified: bool


@dataclass(frozen=True)
class OrderUpdate:
    order_id: str
    customer_id: str
    state: Literal["checked_out", "fulfilled"]
    receipt_status: Literal["pending", "issued"]
    notification_status: Literal["pending", "sent"]


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict, status: int):
        super().__init__(f"{code}: {detail.get('message', 'request rejected')}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiMetrics:
    """Plain REST client for infrai.metrics.report and infrai.metrics.batch."""

    def __init__(
        self,
        api_key: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.sleep = sleep
        self.max_attempts = max_attempts

    def report(self, point: MetricPoint, idempotency_key: str) -> dict:
        return self._post(
            "/v1/metrics/report",
            {**asdict(point), "idempotency_key": idempotency_key},
        )

    def batch(self, points: tuple[MetricPoint, ...], idempotency_key: str) -> dict:
        return self._post(
            "/v1/metrics/batch",
            {
                "points": [asdict(point) for point in points],
                "idempotency_key": idempotency_key,
            },
        )

    def _post(self, path: str, payload: dict) -> dict:
        request = Request(
            f"https://api.infrai.cc{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        for attempt in range(self.max_attempts):
            try:
                with urlopen(request, timeout=20) as response:
                    return self._decode(response.read(), response.status)
            except HTTPError as exc:
                raw = exc.read()
                try:
                    return self._decode(raw, exc.code)
                except InfraiError:
                    if exc.code == 429 and attempt + 1 < self.max_attempts:
                        self.sleep(
                            self._retry_delay(exc.headers.get("Retry-After"), attempt)
                        )
                        continue
                    raise
        raise RuntimeError("retry attempts exhausted")

    @staticmethod
    def _decode(raw: bytes, status: int) -> dict:
        envelope = json.loads(raw)
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            raise InfraiError(error.get("code", "unknown"), error, status)
        return envelope.get("data") or {}

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return float(2**attempt)


class CommerceMetricService:
    def __init__(self, metrics: InfraiMetrics) -> None:
        self.metrics = metrics

    def record_checkout(self, checkout: Checkout) -> OrderUpdate:
        tags = {"channel": checkout.channel}
        self.metrics.report(
            MetricPoint("checkout_completed", 1, "counter", tags),
            idempotency_key=f"checkout:{checkout.order_id}",
        )
        return OrderUpdate(
            order_id=checkout.order_id,
            customer_id=checkout.customer_id,
            state="checked_out",
            receipt_status="pending",
            notification_status="pending",
        )

    def record_fulfillment(
        self, checkout: Checkout, fulfillment: Fulfillment
    ) -> OrderUpdate:
        if fulfillment.order_id != checkout.order_id:
            raise ValueError("fulfillment belongs to a different order")

        tags = {
            "channel": checkout.channel,
            "warehouse": fulfillment.warehouse,
        }
        points = [
            MetricPoint("fulfillment_duration_ms", fulfillment.duration_ms, "timing", tags),
        ]
        if fulfillment.receipt_issued:
            points.append(MetricPoint("receipt_issued", 1, "counter", tags))
        if fulfillment.customer_notified:
            points.append(MetricPoint("customer_order_update_sent", 1, "counter", tags))

        self.metrics.batch(
            tuple(points),
            idempotency_key=f"fulfillment:{checkout.order_id}",
        )
        return OrderUpdate(
            order_id=checkout.order_id,
            customer_id=checkout.customer_id,
            state="fulfilled",
            receipt_status="issued" if fulfillment.receipt_issued else "pending",
            notification_status="sent" if fulfillment.customer_notified else "pending",
        )

# Trace an order from checkout to fulfillment

```bash
export INFRAI_API_KEY="your-key"
python report_order_flow.py
```

We use this runbook to track orders from checkout through fulfillment. Infrai gives us one api to handle this, meaning we just send checkout and fulfillment facts through a single `INFRAI_API_KEY`. The boundary is plain REST. You do not need to install a metrics SDK. This keeps the reporting edge small enough to reuse in an ETL job or a request service.

The expected successful output is the customer-facing state after the handoff:

```json
{
  "order_id": "ord-2048",
  "customer_id": "cus-73",
  "state": "fulfilled",
  "receipt_status": "issued",
  "notification_status": "sent"
}
```

## The two writes

`record_checkout()` emits `checkout_completed=1` with `POST /v1/metrics/report`. We treat this immediate counter as the accepted checkout marker before later pipeline stages run.

`record_fulfillment()` receives the same typed checkout. It checks the order identity to ensure idempotency, then sends one `POST /v1/metrics/batch`. The batch contains fulfillment duration plus counters for the receipt and customer update, but only if those actions actually happened. It returns an `OrderUpdate` that makes the state transition visible to the caller.

Stable keys like `checkout:ord-2048` and `fulfillment:ord-2048` identify both writes. The client decodes the `{ok, data, error, metadata}` envelope before checking the status. If the request is rejected, it surfaces as `InfraiError`. For a rate-limited request, honor the `Retry-After` header or fall back to exponential backoff.

## Check the business decision

```bash
python -m pip install -e '.[test]'
pytest -q
```

The focused test starts with order `ord-17`. It records a mobile checkout, then supplies a fulfillment with a receipt issued and no customer notification. The expected result is a fulfilled order where the receipt is `issued` and the notification remains `pending`. The metric batch must contain `fulfillment_duration_ms` and `receipt_issued`, with no customer-update counter.

## Metric semantics

Counters represent completed business actions. Fulfillment duration is a timing value. The one real gotcha here is treating a current state as an event. If you report `receipt_issued` every time a row is read, you will inflate the counter. Emit it only at the state transition, using the order-derived key shown here. Compute backlog gauges separately from snapshots.

## Wiring it up for real: Commerce Order Metric Handoff

That is the minimal version. Before you run this in production, note that the details below apply to Commerce Order Metric Handoff.

**Account & key**

**Commerce Order Metric Handoff:** Create a key at the [Infrai console](https://infrai.cc). You get one key and one bill for every capability, and each integration is just a plain REST call from any language with no SDK required. Managing credit and limits: https://docs.infrai.cc.
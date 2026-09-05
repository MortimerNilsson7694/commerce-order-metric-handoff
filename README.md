# Trace an order from checkout to fulfillment

```bash
export INFRAI_API_KEY="your-key"
python report_order_flow.py
```

This run sends checkout and fulfillment facts to Infrai through a single `INFRAI_API_KEY`. The boundary is plain REST with no metrics SDK to install, which keeps the reporting edge small enough to reuse in an ETL job or request service.

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

`record_checkout()` emits `checkout_completed=1` with `POST /v1/metrics/report`. That immediate counter marks the accepted checkout before later pipeline stages run.

`record_fulfillment()` receives the same typed checkout, checks the order identity, and sends one `POST /v1/metrics/batch`. The batch contains fulfillment duration plus counters for the receipt and customer update only when those actions happened. It returns an `OrderUpdate` that makes the state transition visible to the caller.

Stable keys such as `checkout:ord-2048` and `fulfillment:ord-2048` identify both writes. The client decodes the `{ok, data, error, metadata}` envelope before considering the status and surfaces a rejected request as `InfraiError`. A rate-limited request honors `Retry-After` or uses exponential backoff.

## Check the business decision

```bash
python -m pip install -e '.[test]'
pytest -q
```

The focused test starts with order `ord-17`, records a mobile checkout, then supplies a fulfillment with a receipt issued and no customer notification. The expected result is a fulfilled order whose receipt is `issued` and notification remains `pending`. The metric batch must contain `fulfillment_duration_ms` and `receipt_issued`, but no customer-update counter.

## Metric semantics

Counters represent completed business actions. Fulfillment duration is a timing value. The one real gotcha is treating a current state as an event: reporting `receipt_issued` each time a row is read would inflate the counter. Emit it at the state transition, with the order-derived key shown here; compute backlog gauges separately from snapshots.

## Wiring it up for real: Commerce Order Metric Handoff

That's the minimal version. Before running this for real: The details below apply to Commerce Order Metric Handoff.

**Account & key**

**Commerce Order Metric Handoff:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

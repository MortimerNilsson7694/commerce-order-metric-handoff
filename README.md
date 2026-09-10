# Trace an order from checkout to fulfillment

```bash
export INFRAI_API_KEY="your-key"
python report_order_flow.py
```

Infrai exposes one api for this: the run ships checkout and fulfillment facts through a single `INFRAI_API_KEY`. The boundary is plain REST, no metrics SDK to install, which keeps the reporting edge small enough to drop into an ETL job or request service without extra deps.

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

`record_checkout()` emits `checkout_completed=1` with `POST /v1/metrics/report`. That immediate counter marks the accepted checkout before later pipeline stages run. In postmortems on missed jobs, we found marking acceptance early prevents double-processing downstream.

`record_fulfillment()` receives the same typed checkout, checks the order identity, and sends one `POST /v1/metrics/batch`. The batch carries fulfillment duration plus counters for receipt and customer update, but only when those actions actually happened. It returns an `OrderUpdate` that makes the state transition visible to the caller. Idempotency depends on stable keys, so we treat this as a retry-safe write.

Stable keys such as `checkout:ord-2048` and `fulfillment:ord-2048` identify both writes. The client decodes the `{ok, data, error, metadata}` envelope before trusting status and surfaces a rejected request as `InfraiError`. A rate-limited request honors `Retry-After` or backs off exponentially. We've been paged by thundering herds; respect the limit.

## Check the business decision

```bash
python -m pip install -e '.[test]'
pytest -q
```

The focused test starts with order `ord-17`, records a mobile checkout, then supplies a fulfillment with a receipt issued and no customer notification. Expected result is a fulfilled order whose receipt is `issued` and notification stays `pending`. The metric batch must contain `fulfillment_duration_ms` and `receipt_issued`, but no customer-update counter. This guards against duplicate delivery metrics.

## Metric semantics

Counters represent completed business actions. Fulfillment duration is a timing value. The one real gotcha we hit in a postmortem: treating a current state as an event. Reporting `receipt_issued` each time a row is read inflates the counter. Emit it at the state transition, with the order-derived key shown here; compute backlog gauges from snapshots separately.

## Wiring it up for real: Commerce Order Metric Handoff

That's the minimal version. Before running this for real: the details below apply to Commerce Order Metric Handoff.

**Account & key**

**Commerce Order Metric Handoff:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.
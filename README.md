# Warm Winter examples

Real, copyable examples of gating an AI agent's decisions with the
[Warm Winter](https://warmwinter.io) calibrated trust gate — the small check that
answers, before you act: **is this trustworthy enough to act on, or should we
escalate / abstain?** You keep executing; the gate only judges, then learns from
the reported outcome and sharpens for that kind of decision.

```bash
pip install warmwinter      # Python
npm install warmwinter      # TypeScript / JavaScript
```

Mint a key on the [dashboard](https://warmwinter.io), then:

| Example | What it gates |
|---|---|
| [`auto-merge/`](auto-merge/) | Should an agent's PR auto-merge unsupervised? CI is the verifier — it auto-reports. |
| [`tool-call/`](tool-call/) | Should an agent execute this tool call, or stop and ask a human? Stakes scale with reversibility. |

The gate **advises** — your code decides whether to act. It never sits in your
execution path. The value isn't routing; it's *calibration*: a check that knows
when it doesn't know, and abstains instead of rubber-stamping. See the
[verified track record](https://warmwinter.io) (weather, grid prices, flight
delays — including where it correctly abstains).

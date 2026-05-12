# YoyoAgent Evals

This directory contains deterministic local evals for behavior that is too broad for a single unit test but still needs a repeatable baseline.

Run all evals:

```bash
python evals/run.py
```

Current scope:

- `context_session_baseline`: protects session history, todo artifact cleanup, resume behavior, old tool output compression, summary memory facts, and summary merge behavior after long-task summary memory has been implemented.

These evals intentionally use fake providers and local assertions. They are not a replacement for unit tests or future model-graded task suites; they are a small guardrail before changing `Session.messages` compaction behavior.

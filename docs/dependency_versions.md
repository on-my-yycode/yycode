# Dependency Versions

This file records the exact dependency versions from the current verified local
development environment. It is informational only; dependency constraints remain
defined in `pyproject.toml`, and reproducible development installs should use
`uv.lock`.

Captured at: 2026-05-25 23:10:47 +0800

Runtime:

- Python: 3.11.8
- uv: 0.7.6

Main dependencies:

```text
anthropic==0.96.0
openai==2.32.0
tiktoken==0.12.0
langgraph==1.1.8
langchain-core==1.3.0
python-dotenv==1.2.2
textual==8.2.4
```

Notes:

- `textual==8.2.4` was verified with Chinese IME input in iTerm.
- `textual==8.2.7` showed Chinese IME input issues during local testing.

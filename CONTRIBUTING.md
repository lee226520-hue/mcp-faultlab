# Contributing

The project values small, reproducible changes over framework-specific magic.

```bash
python3 -m unittest discover -s tests -v
python3 examples/run_demo.py
```

When adding a transport or adapter, include:

1. a fixture or deterministic test;
2. a failure-mode example;
3. documentation for the supported protocol behavior;
4. an explicit note about concurrency, side effects, and redaction.

Please avoid adding a hosted-service dependency to the core package.


# Contributing

Use the [README quickstart](README.md) for a Python 3.12 virtual environment and the frontend toolchain. Original contributions use Apache-2.0. Preserve third-party notices and review changes to native dependencies before publishing binary or container distributions.

Keep feature behavior in `DesignSpec`, geometry construction, and verification. The CLI and browser should call the shared service. New operations need an explicit parameter contract, unsupported-case behavior, and measurements that inspect actual BREP or reopened exports. Add generated geometry fixtures and negative tests; do not commit canned success reports or CAD binaries.

Run the backend tests, frontend tests, production build, and browser workflow against the real backend. For provider work, mock transports verify failure handling only. Record live-model integration separately with the endpoint/model, bounded budget, and observed outcome; keep prompts and private designs outside the repository.

Store application data, Scout caches, downloaded repositories, generated screenshots, export bundles, and benchmark reports outside the source checkout. Include a minimal DesignSpec and relevant installed versions when reporting a kernel problem. Never include API keys or customer-specific design text.

Changes to required measurements should preserve `PASS`, `FAIL`, and `UNKNOWN` semantics. A kernel exception, ambiguity, or unsupported check must remain visible. Performance optimizations must not skip full acceptance checks. UI controls need keyboard access and loading/error states, and must operate on the revision they display.

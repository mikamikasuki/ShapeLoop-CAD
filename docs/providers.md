# Providers

No endpoint or model is configured by default. Structured creation, parameter/feature edits, checking, revision history, and exports remain usable without one. Natural-language controls report that configuration is required.

In Settings, enter the API base URL, exact model ID, and optional server-side key. The endpoint must implement OpenAI-compatible `/models` and `/chat/completions`. A local inference server can use a loopback HTTP URL such as `http://127.0.0.1:11434/v1`; remote endpoints require HTTPS. No model name is assumed available.

The backend also reads explicit environment configuration:

```sh
export SHAPELOOP_MODEL_ENDPOINT='https://your-provider.example/v1'
export SHAPELOOP_MODEL='your-model-id'
export SHAPELOOP_API_KEY='your-key'
shapeloop-cad serve
```

Use connection testing to discover listed models and probe structured response support. ShapeLoop-CAD attempts JSON schema first and falls back to JSON mode or JSON-only text when the endpoint rejects the format. CAD parameter maps are locally validated; the request does not claim strict-schema support that every provider can satisfy. See the [official structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs).

Generation returns a `DesignSpec`; editing returns an `EditProposal` against a named base revision. English and Chinese instructions reach the configured model directly. A local keyword recipe selector does not substitute for model reasoning. Model proposals cannot execute Python or accept geometry. Schema errors, refusals, truncated outputs, authentication errors, and exhausted retry budgets remain explicit errors.

Timeout, maximum output tokens, and attempts bound each operation. Cancellation stops retries and prevents a returned proposal from being used after cancellation; an in-flight HTTP request completes or times out before its synchronous call returns. A successful connection probe is not evidence that a mechanical edit satisfies the user's constraints. Live generation/edit/repair must be exercised separately with the configured provider.

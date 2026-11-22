# JARVIS architecture

## 1. Goals

- Run most of the assistant **locally** on a consumer GPU (8 GB class) without hogging the machine.
- Use a frontier model only for hard work, to save cost and rate limits.
- Make adding a new capability trivial.
- Keep private data private, structurally and not by prompt.

## 2. Tiered routing

```
            ┌───────────────┐
 request ──►│ 1. Rules      │── match ──► run deterministic action
            └──────┬────────┘
                   │ no match
            ┌──────▼────────┐
            │ 2. Local LLM  │── simple ──► answer locally
            │  (router)     │
            └──────┬────────┘
                   │ hard / unsure
            ┌──────▼────────┐
            │ 3. Claude     │── may call ──► 4. MCP tools
            └───────────────┘
```

- The router returns a **schema-constrained** decision. It does not choose tools freely.
- Low confidence escalates to the larger model; a wrong escalation only costs a little quota.
- Every request is written to an episode log (tier used, latency, tokens) so routing quality can be measured and improved.

### Resource policy (keeps the machine usable)

- One model resident at a time; short `keep_alive` so VRAM is free when idle.
- Voice (speech-to-text / text-to-speech) is push-to-talk first, always-on wake word last.
- Scheduled jobs run when the GPU is idle and queue otherwise.

## 3. Capability packs

Each capability is a directory with a manifest:

```yaml
name: example
runtime: { type: mcp_stdio, command: uv, args: [run, python, -m, packs.example.server] }
trust: trusted            # trusted | untrusted_input
scopes: { net: [example.org], secrets: [EXAMPLE_TOKEN] }
schedules: [{ id: daily, cron: "0 7 * * *" }]
```

The core discovers packs and their tools automatically. Packs are MCP servers, so they are process-isolated and replaceable.

## 4. Security model

| Control | How |
|---|---|
| Two planes | Untrusted content (web, email) is only seen by tool-less calls that must emit a fixed JSON schema. Only authenticated, user-originated requests get tools. |
| No autonomous side effects | Sending, posting, paying and trading exist only as *proposals* that need a human approval. |
| Least privilege | Per-pack network and secret scopes. |
| Secrets | Environment / encrypted store; never in code or in the repository. |
| Audit | Every tool call is logged. |

## 5. Roadmap

1. CLI + router + episode log (text only)
2. Messaging surface
3. First read-only pack
4. Persistence and scheduling
5. Voice

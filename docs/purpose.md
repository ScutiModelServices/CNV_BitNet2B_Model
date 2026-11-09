# Purpose

**Kind:** chat messages → text (conversation, small)

**Group:** Conversation

**Tags:** `cpu`, `streaming`, `project-models`, `variants`

| | |
|---|---|
| Input | Chat messages, temperature, max tokens, project. |
| Output | JSON: content, finish reason, usage. Streamable. |
| Runs on | CPU (`transformers`, BitNet b1.58 2B4T). Low memory. The Model variant card chooses the number format (`bfloat16` or `float32`) this machine can hold. |

**Use for:** cheap short replies, simple classification, rewriting, summaries.
**Not for:** tool calls, schemas, thinking (all return 422).

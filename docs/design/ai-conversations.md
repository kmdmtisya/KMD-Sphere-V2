# AI conversation storage (P10-T07)

Decisions: [ADR-0017](../adr/0017-llm-provider-and-key-custody.md) (90-day retention), [AI governance](../ai-governance.md) section 3.

## Tables (migration 0014)

| Table | Holds | Notes |
|---|---|---|
| `ai_conversations` | one chat: owner, optional title, optional portfolio scope, `updated_at` | `updated_at` moves on every new message and is the retention clock |
| `ai_messages` | the turns: `position` (1, 2, ...), `role` (user/assistant), `content`, validated `structured` answer, model, provider | content is capped at 20,000 characters |
| `ai_tool_calls` | one row per tool call: tool name, argument **hash**, ok/error, short error code, duration, correlation id | never arguments or results (the audit event follows the audit policy) |

Every row has `user_id` (cascade on account deletion) and every read or write goes through `owned_by` in `ConversationService`, so another user's conversation answers "not found" exactly like a missing one (ADR-0011). Deleting a conversation removes its messages and tool-call rows; deleting a message keeps its tool-call rows with `message_id` empty.

## Retention

`AI_CONVERSATION_RETENTION_DAYS` (default 90, 1 to 3650). The `purge_ai_conversations` job runs daily at 03:15 UTC through the idempotent job runner and deletes conversations whose last message is older than the period. A user can delete one conversation or all of them at any time (`delete`, `delete_all`); the HTTP routes arrive with the chat API (P10-T06).

## Not stored

Prompts sent to the provider, tool arguments, tool results and provider responses are not stored here and are never logged.

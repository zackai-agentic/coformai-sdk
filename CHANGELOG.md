# Changelog

## Unreleased

- Support managed dashboard writes in both clients with per-call operation UUIDs,
  receipt lookup, deployment reconciliation, and recovery of the sent UUID on errors.
- Add synchronous and asynchronous `sources.upload()` for Knowledge Base files,
  optional semantic retrieval configuration, and organization-scoped multipart
  ingestion. Replace files in place with `source_id` while retaining graph links.
  Preserve asynchronous extraction status and explicit no-retry behavior.

## 0.1.0

- Initial synchronous and asynchronous dashboard/core SDK with typed graph mutations.
- Division/entity/resource management, REST/MCP uploads, schedules, transfers,
  needings, deployment, monitoring, share/embed settings, and catalogs.
- Single-use NDJSON streams, terminal outcomes, approvals, multimodal helpers,
  explicit HTTP/protocol errors, and prefix-preserving URL configuration.
- Dashboard API-key support scoped to selected grants and organization, graph
  batch checks, audit identity, and a server-only short-lived deployment bridge.
- Source documentation, MkDocs/mkdocstrings guides and reference, examples,
  contract tests, bearer regressions, and local build artifacts.

# Changelog

## 0.2.0 — 2026-11-17
- Choose the model per call: `--model flash|pro` on `ask`, `run` and `batch`; a batch task can set its own `"model"`; `setup --model` accepts the short names.
- `status` shows both models with their prices. Skill: when to use flash vs pro.

## 0.1.0 — 2026-11-17
- First release: `ask`, `run` (folder-confined tools, opt-in write/bash), `batch` (parallel), `usage`, `setup`/`status`; exact cost per call.

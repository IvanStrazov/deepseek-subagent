# deepseek-subagent

Cheap DeepSeek sub-agents for Claude Code. Claude hands bulk or mechanical work — read and summarize many files, search a repo, draft or rewrite text, classify rows, simulate users — to a DeepSeek model running in a small tool loop, confined to one folder, and gets back the answer and its exact cost.

```
$ ds.py run "Summarize every SKILL.md here in 3 bullets" --dir ./repo
…answer…
[ds] deepseek-flash: 3 call(s), 11477 in (4736 cached) + 3017 out tokens = $0.0057 peak ($0.0028 off-peak), 2 tool call(s)
```

## What you get
- **`ask`** — one call, no tools, files attached as text. Cheapest.
- **`run`** — an agent with `list_files` / `read_file` / `grep`, confined to a folder; `--write` adds `write_file`, `--bash` adds a shell.
- **`batch`** — many `run`s in parallel from a JSONL file, one result file per task, total cost at the end.
- **Cost on every call**, from DeepSeek's own token counts (cache hits included), plus a local spend log (`usage`).
- Stdlib-only Python 3.9+, no dependencies, no MCP server.

## Install
```
/plugin marketplace add IvanStrazov/deepseek-subagent
/plugin install deepseek-subagent@deepseek-subagent
```
Then say "set up the DeepSeek sub-agent": Claude runs `ds.py setup --key-file <your .env>` (a file with `DEEPSEEK_API_KEY=…`), or export `DEEPSEEK_API_KEY`. The key is read at call time and never printed or copied.

## Safety and privacy
- File tools cannot leave the given folder. `--bash` is a real shell as you, **not a sandbox**: a deny-list only refuses the obvious (push, curl/wget, ssh, installs, `rm -rf /`). Use it for trusted folders only.
- Everything the sub-agent reads is sent to DeepSeek's API. The skill tells Claude to ask before sending private material and to keep `.env`/key files out.
- Results are treated as another model's output: Claude verifies what matters before relying on it.

## Prices
Per 1M tokens, peak hours (off-peak is half), as of 2026-11-17: `deepseek-flash` $0.30 input / $0.006 cached / $1.20 output; `deepseek-v4-pro` $1.32 / $0.044 / $3.96. Edit `PRICES` in `scripts/ds.py` if they change.

## Files
- `~/.claude/deepseek/config.json` — key file path and model (no key inside)
- `~/.claude/deepseek/usage.jsonl` — one line per task: tokens and cost

MIT license.

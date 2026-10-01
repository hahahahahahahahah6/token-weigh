# tokw — token-weigh

You've done it too: pasted a 40k-token debug log into a conversation, watched your context budget evaporate, and spent the rest of the session fighting the model for attention. **tokw** weighs your files in tokens *before* you paste them in — so you know exactly what each file costs your budget, ahead of time.

## Install

No dependencies, standard library only. Python 3.9+.

```bash
git clone https://github.com/hahahahahahahahah6/token-weigh
cd token-weigh
# optional: put tokw.py on your PATH or symlink it as `tokw`
chmod +x tokw.py
```

## Usage

Weigh individual files:

```bash
python3 tokw.py debug.log server.py notes.md
```

Walk a directory recursively (skips hidden dirs, `__pycache__`, `node_modules`, `.git`; skips binary files via null-byte sniffing):

```bash
python3 tokw.py -r src --ext .py,.md
```

Set a context budget and get machine-readable output:

```bash
python3 tokw.py -r . --budget 200000 --json
```

### Example output

```text
$ python3 tokw.py -r ./src --ext .py,.md
path                          chars  est. tokens
------------------------------------------------
src/legacy_parser.py            48210       12052  << over 10% of budget
src/handlers.py                 31508        7877
docs/design.md                  12440        3110
src/utils.py                     8902        2226
------------------------------------------------
TOTAL: 25265 est. tokens = 12.6% of budget (200000)
```

Exit code is always 0 — this is informational. Exit code 2 means a path couldn't be read.

## How the estimate works

tokw is **not a tokenizer**. It uses a documented heuristic:

- each CJK / CJK-punctuation character (Chinese, Japanese kana/kanji, Korean hangul, fullwidth forms) ≈ **1 token**
- every other character ≈ **1/4 token**

The per-file total is rounded to the nearest whole token. This mirrors how modern tokenizers actually behave: CJK characters usually encode as one token each, while ASCII-heavy code and prose average about four characters per token. It won't match any specific model's exact count — it tells you the order of magnitude, which is what you need to decide *what goes in*.

## Differentiation: tokw vs mcp-tax

Same household, different axis. [mcp-tax](https://github.com/hahahahahahahahah6/mcp-tax) weighs **MCP server schemas** — the hidden context tax your agent pays every turn for tools it never calls. **tokw** weighs **your files** — the explicit cost of what you paste or attach into a conversation. One audits what the agent brings to the table; the other audits what *you* bring to the table. Run both and you know where your whole context budget actually goes.

## License

MIT — see [LICENSE](LICENSE).

# Ollama setup for the pipeline

The pipeline calls Ollama over HTTP for both the LLM (`qwen3:14b`) and the embedding model (`nomic-embed-text`). It's designed to run with Ollama on a separate GPU host called over the network, but a single-machine setup works fine too.

## Configuration

Set in `.env`:

```bash
OLLAMA_HOST=http://<your-ollama-host>:11434
OLLAMA_MODEL=qwen3:14b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_PARALLEL=4
```

For a remote Ollama, the daemon must bind a non-loopback interface. Start it with:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

…and ensure port 11434 is reachable from the pipeline host.

Pull the models on the GPU host:

```bash
ollama pull qwen3:14b
ollama pull nomic-embed-text
```

## VRAM math (RTX 4080, 16 GB)

`qwen3:14b` Q4_K_M weights are ~12 GB. The remaining 4 GB is shared between KV cache slots (`OLLAMA_NUM_PARALLEL` × per-slot KV at the requested `num_ctx`) and other system overhead.

| `NUM_PARALLEL` | Per-slot KV at 16 k ctx | Total VRAM | Fits? |
|---|---|---|---|
| 2 | 1.4 GB × 2 = 2.8 GB | 14.8 GB | ✓ |
| 4 | 1.4 GB × 4 = 5.6 GB | 17.6 GB | ✗ (CPU spill) |
| 4 + `num_ctx=8192` | 0.7 GB × 4 = 2.8 GB | 14.8 GB | ✓ |

Pipeline scripts default to `num_ctx=8192` for this reason. Bumping to 16 k spills to CPU and runs ~6× slower.

## GPU stranding (recovery procedure)

If another process held the GPU when `qwen3:14b` first loaded, Ollama silently falls back to CPU and stays there. Symptom: `/api/ps` shows `size_vram: 0` even though the model is loaded.

To fix:

```bash
# Unload
curl -s "$OLLAMA_HOST/api/generate" -d '{"model":"qwen3:14b","keep_alive":0}' > /dev/null

# Force a fresh load (lands on GPU if it's free now)
curl -s "$OLLAMA_HOST/api/generate" -d '{"model":"qwen3:14b","prompt":"hi","stream":false,"think":false,"options":{"num_predict":1}}' > /dev/null

# Verify VRAM
curl -s "$OLLAMA_HOST/api/ps"
```

If `size_vram` is still 0 after this, something else on the GPU host is holding the GPU (Docker container, another model, browser GPU process). `nvidia-smi` on the host will show the offender.

## qwen3 reasoning suppression

The `/no_think` directive in the prompt is silently ignored on `qwen3:14b`. The model emits `<think>...</think>` tokens that consume the entire `num_predict` budget, leaving `response: ""` and `done_reason: "length"`.

The suppression that actually works is Ollama's native reasoning toggle — pass `"think": false` at the top level of the `/api/generate` payload (NOT inside `options`):

```json
{
  "model": "qwen3:14b",
  "prompt": "...",
  "stream": false,
  "think": false,
  "options": {"temperature": 0, "num_predict": 500, "num_ctx": 8192}
}
```

All five LLM-using scripts in this pipeline pass `"think": false`. Without it, Stage 1 ran ~9 s/row; with it, ~0.7 s/row (~10× speedup).

Confirmed working on Ollama 0.17.1.

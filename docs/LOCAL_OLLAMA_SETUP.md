# Local Qwen3 4B Instruct setup

The web dashboard can run either Google Gemini through its external API or a
TradingAgents-specific variant of `qwen3:4b-instruct` locally through Ollama.
The variant keeps the same Qwen weights but embeds a 16K context window so the
analyst prompt and subsequent tool responses do not hit Ollama's 4096-token
default. The local provider sends prompts to the server-controlled endpoint at
`http://localhost:11434/v1`; API keys and prompts are not sent to Gemini for a
local run.

## 1. Install and verify Ollama

Install the current Ollama for Windows from <https://ollama.com/download/windows>.
Ollama should remain running in the Windows system tray while TradingAgents is
using the local provider.

Verify the service:

```powershell
ollama --version
ollama list
```

Download the exact dashboard model if it is not already listed:

```powershell
ollama pull qwen3:4b-instruct
ollama create tradingagents-qwen3:4b-instruct-16k -f .\ollama\qwen3-4b-instruct-16k.Modelfile
```

Run the `ollama create` command from the TradingAgents repository root. It
creates a small local manifest that reuses the downloaded Qwen weights; it does
not download a second 2.5 GB copy. The dashboard deliberately uses
`tradingagents-qwen3:4b-instruct-16k` for both quick and deep agents so only one
model occupies memory.

## 2. Apply conservative 4 GB VRAM settings

For an NVIDIA RTX 3050 Laptop GPU with 4 GB VRAM, keep one request/model at a
time and reduce the KV-cache footprint:

```powershell
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
setx OLLAMA_NUM_PARALLEL 1
setx OLLAMA_MAX_LOADED_MODELS 1
```

Exit Ollama completely from the system tray and launch it again after running
`setx`; those values apply only to newly started processes. The model-specific
Modelfile controls the 16K context, while these server settings enable the more
compact q8 KV cache. Some layers will remain in system RAM because 4 GB VRAM is
not enough for the model plus a 16K cache; GPU acceleration remains active, but
generation will be slower than with a 4K context.

## 3. Configure TradingAgents

In the project `.env`, keep the local endpoint server-controlled:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434/v1
WEB_RUN_QUEUE_LIMIT=1
```

`WEB_RUN_QUEUE_LIMIT=1` prevents multiple analyses from competing for the same
4 GB GPU. Keep `GOOGLE_API_KEY` configured only if Google Gemini should remain
available as the other dashboard choice.

Install and start the dashboard from the project directory:

```powershell
conda activate tradingagents
pip install -e ".[web]"
tradingagents-web
```

Open <http://127.0.0.1:8000>, log in, and select one of:

- **Google Gemini** for the external Gemini API.
- **Qwen3 4B Instruct (Local GPU)** for Ollama on this laptop.

## 4. Verify GPU execution

While a local analysis is producing output, run:

```powershell
ollama ps
nvidia-smi
```

The `PROCESSOR` column in `ollama ps` should show `100% GPU` or a GPU-heavy
CPU/GPU split, and `nvidia-smi` should show Ollama using VRAM. A mixed split is
valid but slower. If Ollama falls back to CPU, update the NVIDIA driver, restart
Ollama, close other GPU-heavy applications, and retry with the 8K context.

## Troubleshooting

- **Connection refused / Ollama unavailable**: launch the Ollama Windows app and
  confirm `Invoke-RestMethod http://localhost:11434/api/tags` succeeds.
- **Model not found**: run `ollama pull qwen3:4b-instruct`, then recreate the
  dashboard alias with `ollama create tradingagents-qwen3:4b-instruct-16k -f
  .\ollama\qwen3-4b-instruct-16k.Modelfile`.
- **Request exceeds context size 4096**: the base model was selected or the
  alias has not been created. Confirm the dashboard uses
  `tradingagents-qwen3:4b-instruct-16k` and recreate it using the command above.
- **Out of memory or very slow output**: close games/creative applications and
  keep `OLLAMA_NUM_PARALLEL=1`. The 16K model will use both GPU and system RAM
  on a 4 GB RTX 3050.
- **Gemini reports a missing key**: add `GOOGLE_API_KEY` to `.env`; this is not
  required for Qwen/Ollama runs.
- **Local Qwen quality differs from Gemini**: a 4B local model is materially
  smaller than hosted Gemini. Use shallow research and one or two analysts for
  the first test, then increase depth after confirming stability.

Firebase authentication, Firestore history, Yahoo market data, and optional
news/data sources still use the internet. Selecting Qwen makes the LLM local;
it does not make the entire TradingAgents application offline.

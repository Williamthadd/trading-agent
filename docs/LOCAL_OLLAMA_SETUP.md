# Local Llama 3.2 3B setup

The standalone React frontend can select either Google Gemini through its
external API or a TradingAgents-specific variant of `llama3.2:latest` locally
through Ollama. FastAPI is a separate backend API; it does not serve the
Bloomberg-style UI. The variant uses the same Llama 3.2 3B weights but embeds a
16K context window so analyst prompts and subsequent tool responses do not fall
back to Ollama's 4096-token runtime default. The local provider sends prompts
only to the server-controlled endpoint at `http://localhost:11434/v1`; it does
not send those prompts to Gemini.

## 1. Install and verify Ollama

Install the current Ollama for Windows from <https://ollama.com/download/windows>.
Ollama must remain running in the Windows system tray while TradingAgents uses
the local provider.

Verify the service:

```powershell
ollama --version
ollama list
```

Download the base model and create the exact 16K application alias:

```powershell
ollama pull llama3.2:latest
ollama create tradingagents-llama3.2:16k -f .\ollama\llama3.2-16k.Modelfile
```

Run `ollama create` from the TradingAgents repository root. The alias reuses
the downloaded model layers; it does not download another full copy. Confirm
that the context parameter is present:

```powershell
ollama show tradingagents-llama3.2:16k
```

The output should list `num_ctx 16384`. The backend deliberately requires this
alias for both quick and deep agents so only one model occupies memory. Do not
replace it with plain `llama3.2:latest` in a frontend request: on this 4 GB GPU
that can revert to a 4096-token allocation and reject normal TradingAgents
prompts.

## 2. Apply conservative 4 GB VRAM settings

For an NVIDIA RTX 3050 Laptop GPU with 4 GB VRAM, keep one request and one
loaded model at a time, and reduce the KV-cache footprint:

```powershell
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
setx OLLAMA_NUM_PARALLEL 1
setx OLLAMA_MAX_LOADED_MODELS 1
```

Exit Ollama completely from the system tray and launch it again after running
`setx`; those settings apply only to newly started processes. The Modelfile
controls the 16K context, while these server settings enable a smaller q8 KV
cache and prevent concurrent models from competing for the same GPU. A mixed
CPU/GPU split is expected with a 16K context on 4 GB VRAM and is slower than a
4K allocation, but it is large enough for the agent/tool prompts that the 4K
configuration rejected.

## 3. Configure TradingAgents

In the project `.env`, keep the local endpoint server-controlled:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434/v1
WEB_RUN_QUEUE_LIMIT=1
WEB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

`WEB_RUN_QUEUE_LIMIT=1` prevents multiple analyses from competing for the same
GPU. Keep `GOOGLE_API_KEY` configured only if Google Gemini should remain
available as the other frontend choice. `WEB_CORS_ORIGINS` must list the exact
React origins; do not replace it with wildcard `*`, add a path, or omit the
port. CORS does not replace Firebase Bearer-token verification.

Install and start the backend API from the project directory:

```powershell
conda activate tradingagents
python -m pip install -e ".[api]"
tradingagents-api
```

The backend runs at <http://127.0.0.1:8000>; its root returns API metadata, not
the UI. Create and run the standalone React + Vite frontend by following
[`REACT_FRONTEND_PROMPT.md`](REACT_FRONTEND_PROMPT.md). Its local environment
must point to the backend:

```dotenv
VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000
```

Run `npm install` and `npm run dev` in the frontend repository, then open
<http://localhost:5173>, log in, and select one of:

- **Google Gemini** for the external Gemini API.
- **Llama 3.2 3B (Local / Ollama)** for the local 16K model.

Start with Shallow research and one analyst. Increase the analyst count or
research depth only after that run completes successfully; each additional
debate round adds prior reports to later prompts and increases execution time.

## 4. Verify context and GPU execution

While a local analysis is producing output, run:

```powershell
ollama ps
nvidia-smi
```

For the local application model, `ollama ps` should show `CONTEXT 16384` and a
GPU or mixed CPU/GPU value under `PROCESSOR`. A mixed split still means GPU
acceleration is active. If it shows context 4096, recreate the alias and restart
the TradingAgents run.

You can also verify that an input larger than 4K is accepted:

```powershell
$text = ("Market data context for AAPL. " * 1200)
$body = @{
  model = "tradingagents-llama3.2:16k"
  stream = $false
  messages = @(@{ role = "user"; content = $text + " Summarize in one sentence." })
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://localhost:11434/api/chat `
  -ContentType "application/json" -Body $body
```

## Troubleshooting

- **Connection refused / Ollama unavailable**: launch the Ollama Windows app and
  confirm `Invoke-RestMethod http://localhost:11434/api/tags` succeeds.
- **Model not found**: run `ollama pull llama3.2:latest`, then recreate the alias
  with `ollama create tradingagents-llama3.2:16k -f
  .\ollama\llama3.2-16k.Modelfile`.
- **Request exceeds context size 4096**: the base model was selected or the
  alias has not been created. Confirm the frontend selected
  `tradingagents-llama3.2:16k`, recreate it, and restart the backend API.
- **Request exceeds context size 16384**: use Shallow research, select fewer
  analysts, and start a new run. Raising context beyond 16K on a 4 GB GPU can
  push more layers into system RAM and make generation substantially slower.
- **Out of memory or very slow output**: close games and creative applications,
  stop other models with `ollama stop <model>`, and keep
  `OLLAMA_NUM_PARALLEL=1`.
- **Gemini reports a missing key**: add `GOOGLE_API_KEY` to `.env`; it is not
  required for Llama/Ollama runs.
- **Local Llama quality differs from Gemini**: a 3B local model is materially
  smaller than hosted Gemini. Prefer English output, Shallow depth, and one or
  two analysts when reliability matters.

Firebase Authentication, Firestore history, Yahoo market data, and optional
news/data sources still use the internet. Selecting Llama makes the LLM local;
it does not make the entire TradingAgents application offline. The frontend
must send a Firebase ID token as a Bearer token on every protected backend call.
Firebase service-account JSON, `GOOGLE_API_KEY`, and all other server secrets
remain in the backend environment only and must never be copied into the React
repository or its `VITE_*` variables.

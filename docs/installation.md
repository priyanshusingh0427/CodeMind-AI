# Installation Guide (Windows, Linux, macOS)

Everything is free and runs offline on an ordinary laptop (8–16 GB RAM, no GPU).

## 1. Install Python 3.11 or newer
- **Windows:** download from <https://www.python.org/downloads/>. In the installer tick **"Add python.exe to PATH"**.
- **macOS:** `brew install python@3.11` (or the python.org installer).
- **Linux (Ubuntu/Debian):** `sudo apt install python3.11 python3.11-venv`.

Check: `python --version` (Windows) or `python3 --version` (macOS/Linux) → 3.11 or higher.

## 2. Get the project and open it in VS Code
Unzip/clone the `CodeMind-AI` folder, then *File → Open Folder…* in VS Code. Install the **Python** extension
when VS Code suggests it.

> **Windows "Extract All" tip:** extracting `CodeMind-AI.zip` often creates `CodeMind-AI\CodeMind-AI\`. Open (and
> `cd` into) the **inner** folder, the one that contains `app.py`. Running commands from the outer folder is the most
> common cause of `ModuleNotFoundError: No module named 'evaluation'` (or `core`, `config`).

## 3. Create a virtual environment
```bash
cd CodeMind-AI
python -m venv .venv
# Windows (PowerShell):   .venv\Scripts\Activate.ps1
# Windows (cmd):          .venv\Scripts\activate.bat
# macOS / Linux:          source .venv/bin/activate
```
If PowerShell blocks the script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
In VS Code select the interpreter `.venv` (Ctrl+Shift+P → *Python: Select Interpreter*).

## 4. Install dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Install Ollama and a coding model
1. Download Ollama from <https://ollama.com/download> and install it (it runs in the background).
2. Pull a model:

| Model | Download | Suggested RAM | Notes |
|---|---|---|---|
| `qwen2.5-coder:1.5b` (default) | ~1 GB | 8 GB | Fastest |
| `qwen2.5-coder:3b` | ~1.9 GB | 8 GB | Better reasoning |
| `qwen2.5-coder:7b` | ~4.7 GB | 16 GB | Best quality, slow on CPU |

```bash
ollama pull qwen2.5-coder:1.5b
ollama list            # should show the model
```

## 6. Configure (optional)
```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```
Edit values if needed (model name, timeouts, sandbox limits). Most settings can also be changed on the
**Settings** page and are saved to `data/user_settings.json`. No API keys are required.

## 7. Start the app
```bash
streamlit run app.py
```
Your browser opens <http://localhost:8501>. The sidebar shows whether the LLM and the sandbox are ready.

### Check everything in one go
```bash
python check_setup.py                   # Python, packages, database, static analysis, Ollama + one real AI fix, Docker
python check_setup.py --skip-llm        # same, without the (slow) model call
python check_setup.py --build-sandbox   # also builds the Docker sandbox image if it is missing
```
Each line is `[OK]`, `[WARN]`, `[FAIL]` or `[SKIP]` with a hint. The summary is saved to `data/setup_check.json`.
`[WARN] Docker` is fine if you do not need code execution; `[FAIL]` lines must be fixed before running the benchmark.
The script works from any folder (`python C:\path\to\CodeMind-AI\check_setup.py`).

## 8. Optional: isolated validation environment (Docker)
Needed only to **run** tests on submitted/AI code. Without it, CodeMind AI never executes code.
1. Install Docker Desktop (Windows/macOS) or Docker Engine (Linux) and start it.
2. Build the sandbox image once (or use *Settings → Build sandbox image*):
   ```bash
   docker build -t codemind-sandbox:latest sandbox/
   ```
3. Every test run uses: `--network none`, user `65534` (non-root), `--cpus`, `--memory`, `--pids-limit 64`,
   `--read-only` root FS with a small `noexec` tmpfs, `--cap-drop ALL`, `no-new-privileges`, a read-only mount
   of a temporary folder only, a timeout, and output truncation.

## 9. Run the unit tests
```bash
pytest
```
Docker end-to-end tests are skipped automatically if the sandbox image is missing.

## 10. Run the benchmark experiments
Use the root-level `run_benchmark.py`. It works from any folder and draws the charts at the end.
```bash
python run_benchmark.py --limit 10                 # trial: first 10 eval examples, all three methods
python run_benchmark.py                            # MAIN run: full eval split (92 examples), all three methods
python run_benchmark.py --methods static           # quick baseline only (about 30 s)
python run_benchmark.py --methods llm_only,hybrid  # only the LLM methods; the static results are kept
python run_benchmark.py --resume                   # continue an interrupted run where it stopped
python run_benchmark.py --model qwen2.5-coder:3b   # another Ollama model
```
(`python -m evaluation.benchmark_runner ...` and `python -m evaluation.visualization` still work when run from the
project folder.)

- **Time:** LLM methods take roughly *examples × 2 programs × model latency*. With `qwen2.5-coder:1.5b` on a CPU,
  expect a few seconds to a minute per program; the progress line shows an ETA. Run `--limit 10` first.
- **Interruptions:** every result is saved to `evaluation/results/progress_*.jsonl` as soon as it is measured. If the
  laptop sleeps or you press Ctrl+C, rerun the same command with `--resume`.
- **Main vs trial results:** only a full run on the eval split (no `--limit`, no `--split`, no `--dataset`) updates
  `evaluation/results/summary.json`, which the report and the **Analytics → Benchmark results** tab use. Any other
  run goes to `summary_trial.json` (charts prefixed `trial_`) and can be viewed in the app with the *Latest trial run*
  switch. **Never report trial numbers.**
- Keep Docker running during the main run so repairs are scored with held-out tests; otherwise repair metrics are
  recorded as *not measured*.

Optional external data: `python datasets/prepare_quixbugs.py` downloads QuixBugs (MIT) and converts it; then
`python run_benchmark.py --dataset datasets/external/quixbugs.json --split external`. See
[datasets/README.md](../datasets/README.md).

## 11. Demo without a model
`python tests/mock_ollama_server.py --port 11435`, then set `OLLAMA_HOST=http://localhost:11435` and
`OLLAMA_MODEL=mock-coder`. It returns canned answers – useful to test the UI, never for results.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `streamlit: command not found` | Activate the venv, or run `python -m streamlit run app.py` |
| Sidebar says *LLM offline* | Start Ollama (`ollama serve` or open the app), check `OLLAMA_HOST`, run `ollama pull <model>` |
| *Model not installed* | The name in Settings must match `ollama list` exactly |
| AI step times out | Use the 1.5b model, raise *Request timeout* in Settings, close heavy apps |
| *Static-only mode* | Docker not installed/running or image not built (see step 8) |
| Docker permission denied (Linux) | `sudo usermod -aG docker $USER`, then log out and in |
| `ModuleNotFoundError: No module named 'evaluation'` (or `core`, `config`) | You are not in the folder that contains `app.py` (often a nested `CodeMind-AI\CodeMind-AI`). `cd` into it, or use `python run_benchmark.py` / `python check_setup.py`, which work from anywhere |
| `ModuleNotFoundError` for a package (e.g. `streamlit`, `radon`) | Activate the venv, then `pip install -r requirements.txt`. `python check_setup.py` lists what is missing |
| Benchmark stopped half-way | Rerun the same command with `--resume` |
| `[FAIL] LLM debugging call` in `check_setup.py` | Model too slow or out of memory: try `qwen2.5-coder:1.5b`, set `LLM_TIMEOUT=300` in `.env` |
| Pylint message in results | Pylint missing or timed out; AST checks still work |
| Port 8501 busy | `streamlit run app.py --server.port 8502` |
| Database errors after upgrades | Delete `data/codemind.db` (history is lost) |

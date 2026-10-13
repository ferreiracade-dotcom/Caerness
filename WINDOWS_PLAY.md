# Play Caerness free on Windows

The narrative policy now permits compatible creative biographies, memories and
significant new people/institutions. Important objective additions are reviewed and
persisted in the campaign; ordinary anecdotes need no approval ceremony. See
[supported invention and limits](docs/narrative-authoring.md). The package is ready
for a controlled owner-side playtest; narrative quality is not yet accepted.

No subscription, API key or paid account is needed. You need a Windows computer,
enough memory for a local model, and internet access for the initial downloads.
The game and model then run locally. A small CPU-only computer may be too slow for
enjoyable play; model files are not their full inference memory requirement.

## First launch

1. Install **Python 3.12 or later** from [python.org](https://www.python.org/downloads/windows/), including the Python launcher (`py`).
2. [Download the complete local-AI ZIP](https://github.com/ferreiracade-dotcom/Caerness/archive/refs/heads/feat/free-local-ai.zip). Sign in to GitHub if required, choose **Extract All**, and open the extracted folder.
3. Double-click **Play Caerness.cmd**. It prepares the Python environment/NumPy, then checks RAM, GPU and dedicated VRAM. Keep its window open while playing.
4. If Ollama is missing, permit opening the [official Windows installer](https://ollama.com/download/windows), install it, then return and press Enter. Windows 10 22H2 or later is required. Local models require no Ollama account.
5. Choose a displayed model. The launcher explains estimated download size and GPU-memory candidacy. **Type YES** to permit a download; Enter or any other answer declines. Installed models are reused.
6. The launcher references downloaded weights with a bounded **8K context** and tests a **real structured model reply**. First loading can take a while. It will not open the game if that check fails. The diagnostic is saved in **game/local-inference-check.json**; it is not proof of gameplay quality.
7. Your browser opens at **http://127.0.0.1:8765**. Create a character or select an established living character. Explore, converse and make decisions in ordinary language.

Ollama software occupies roughly 4 GB, plus the Python environment. Additional
model downloads are approximately 3.4 GB for Qwen3.5 4B, 6.6 GB for Qwen3.5 9B,
8 GB for Gemma 4 12B, and 16–19 GB for larger comparisons. Displayed ceilings allow
library changes. Windows, context and graphics buffers need additional memory.
Close memory-heavy applications. Explicit Q4_K_M tags avoid old Llama defaults,
changing `latest` aliases and unnecessarily severe quantisation.

Qwen3.5 9B is a **provisional first candidate** with 16 GB+ RAM. Compare Gemma 4 12B
with 24 GB+ RAM; 48 GB+ RAM opens larger comparisons. This is not a measured literary
ranking. VRAM informs full-offload candidacy; CPU/partial offload can take minutes.
Unknown RAM prevents recommendations; shared memory is never counted as dedicated
VRAM. The 4B fallback is diagnostic, not an accepted substitute for narrative quality.

## LM Studio alternative

Install [LM Studio](https://lmstudio.ai/). In its model browser, choose a **local
GGUF Q4_K_M** Qwen3.5/Gemma 4 model appropriate to your hardware and confirm its
download yourself. Load one model, set context to **8192**, turn thinking off, and
start its local server on port **1234**. Double-click **Play with LM Studio.cmd**
and choose its model ID. The same real inference diagnostic runs without an API key.
Keep LM Studio running. Caerness does not automate or claim to verify its download GUI.

## Playing and saving

- **Enter:** send; **Shift+Enter:** new line; **Ctrl+K:** focus input.
- **Alt+1–5:** Story, World, Commitments, History, Character; **Escape:** close panels.
- **History:** resume persistent conversations. Ordinary dialogue does not automatically spend time. Important ambiguous commitments can require review; resources, authority and NPC willingness remain engine-controlled.
- Close the launcher to stop. Reopen to resume; the selected Ollama model is remembered.
- Close the game, then use **Change Local Model.cmd** to select another model. Your character, relationships and campaign remain intact.
- Your save is **game/narrative-session.db**. Back it up while the game is stopped. The opening **data/caerness.db** stays untouched. Keep the extracted folder when updating. Real-world absence never advances game time.

## Updating after the first Windows playtest

1. Close Caerness and its launcher. Keep the old folder as a backup.
2. Download and extract the updated branch ZIP into a **new** folder.
3. Copy the old **game** folder into the new folder, retaining its files. This preserves
   your campaign, pending responses, history and any SQLite journal files. Do not
   delete files ending in `-wal` or `-shm`, and do not copy a running campaign.
4. Launch **Play Caerness.cmd** in the new folder. Your installed model is reused;
   there is no compulsory download or new campaign.
5. Open **Settings → Advanced options & diagnostics → Retry unfinished response**.
   This resumes the latest unfinished response in the selected conversation, rather
   than sending your original action again. Completed requests are never replayed.

Failures now distinguish timeout, unavailable service, invalid/incomplete output,
context overflow, reported memory exhaustion and a failed/repeated continuation.
The request ID and phase appear in diagnostics. **Copy Diagnostics** copies model
settings, RAM/GPU/driver information, loaded Ollama GPU allocation and recent
request counts/timings. It excludes dialogue, world facts, credentials, endpoints
and personal folder paths. Paste this report into the review/chat when asking for help.
Hardware collection can take a little while; no Python or SQLite commands are needed.

The pause button stops at a safe boundary; an in-flight model call may still need
to finish or time out. A received response can then be resumed without another
model call. Confirmed actions and pending continuations are committed before the
next slow call, so closing the launcher does not force already-completed actions
to repeat.

## GTX 1050 Ti / 16 GB RAM: realistic next test

Your Windows installation worked. CPU-only **9B is not a practical default**: your
test timed out, with roughly 205 seconds of prompt processing and 2.1 generated
tokens/second. Keep the installed 4B for the software recovery check, but its
storytelling/planning quality and CPU latency have **not** passed gameplay acceptance.
The launcher no longer recommends 9B solely because it fits system RAM.

Ollama's [current NVIDIA support documentation](https://docs.ollama.com/gpu) lists
the GTX 1050 Ti (compute capability 6.1). It specifies driver **570 or newer** for
capabilities 5.0–6.2. Check/install the latest compatible Windows driver using
NVIDIA's official installer, restart Windows, then quit Ollama from its tray icon
before launching Caerness. When starting a new Ollama server on NVIDIA Windows,
Caerness defaults to **Vulkan disabled**, leaving CUDA available. It does not kill
an existing server or silently override an explicit environment setting.

Disabling Vulkan does **not** itself disable CUDA. Whether CUDA actually loads on
your PC remains to be verified; `size_vram` in Copy Diagnostics shows whether Ollama
allocated GPU memory. A 4 GB card must not be assumed to fit 9B efficiently.

A free alternative is **LM Studio with a local 4B Q4_K_M GGUF and its NVIDIA CUDA
runtime**, checking actual GPU offload in its loading controls. Text-only loading
can avoid unnecessary vision-projector memory where supported. Match Caerness's
context budget to the server; output/context controls are in Settings. The Ollama
alias defaults to 8192 and the launcher preserves saved custom budgets when reusing
the same model. Larger context is not a cure for slow CPU inference.

Smaller models may fit/speed up more easily, but that is a quality trade-off, not a
demonstrated solution. Using another existing computer with more GPU memory is also
free of token charges. No paid API is required. If CUDA/LM Studio cannot make the
4B sufficiently fast **and** reliable, this CPU configuration has not met the goal;
there is no evidence that merely increasing the timeout will make it enjoyable.

[Reproduced failures, tests and genuine measurements](docs/windows-gameplay-recovery.md).

Free-local setup rejects non-loopback endpoints, cloud tags and Ollama aliases with
remote-model metadata. Inherited cloud API keys are not sent to the local service.
When it starts Ollama itself, it sets `OLLAMA_NO_CLOUD=1`; for an already-running
Ollama app, you can also disable cloud in Ollama settings. Caerness's checks remain
in force. Only initial software/model downloads contact distributors.

## Test your model's gameplay

Close the game and double-click **Test Local AI.cmd**. It records real replies on a
**separate test campaign**, in a new **runs/local-gameplay-DATE-TIME** folder: twenty
NPC dialogue turns, an unfamiliar request, time passage and ordinary life. CPU runs
can take a long time. Its test player approves only independently verified, complete
displayed scopes in that disposable campaign. It never approves an unresolved scope
or changes your played campaign; refusal and partial progress are legitimate outcomes.

Read **transcript.json** for player words, exact model packets/replies, engine results
and model latency. **evaluation.json** records hardware/model/gate status;
**reload-state.json** verifies continuity. Recorded responses need qualitative review:
engaging prose, coherent personality, grounded facts and enjoyable pacing. A successful
connection or twenty generated replies alone is not acceptance.

To test LM Studio, run **Test Local AI.cmd --local-server lmstudio** from the extracted
folder's terminal, or add that option to a shortcut. Model settings and diagnostics
stay outside the main story. [Runtime/model assessment](docs/local-ai.md) and
[test evidence](docs/local-ai-evidence.md) distinguish genuine inference from mocks.

## Troubleshooting

- **Ollama not found:** finish installation and reopen the launcher.
- **Download declined:** nothing is downloaded; reopen when ready.
- **Insufficient disk/RAM:** choose a smaller candidate or a better-equipped PC.
- **Service unavailable:** open Ollama/LM Studio and check its local server.
- **Structured check fails:** update the runtime or choose another local model.
- **Context/output limit:** the turn is refused rather than silently dropping conditions. Narrow the request or start another conversation; old conversations stay saved.
- **Slow replies:** close other applications and compare a smaller model. The loaded-model diagnostic reports GPU allocation; speed depends strongly on hardware.

Windows installation/launch succeeded in the owner's test. CUDA offload and the
larger-model literary comparison remain owner-side acceptance gates. Linux inference and mocked policy tests are separate
kinds of evidence. A working local server alone does not mean the game is enjoyable.

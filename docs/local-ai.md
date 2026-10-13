# Free local inference: decision and acceptance

Research: 13 October 2026. Base: PR #6 head
`a9ec492ca26716fb2da6deeefffffb9176fba368`, preserving #5/#4/#3.
Reuse the OpenAI-compatible gateway, planning contracts and responsive client.
No new provider abstraction, gameplay handler, simulation expansion or canon change.

## Runtime assessment

| Runtime | Windows and setup | Structure/gateway | Hardware and context | Decision |
|---|---|---|---|---|
| Ollama | Native installer, discoverable CLI and model pull/create APIs | Existing OpenAI chat endpoint, JSON/schema and thinking controls; engine validates meaning | NVIDIA, AMD/ROCm/Vulkan, CPU/partial offload; bounded model alias | Default for consent-based automatic startup |
| LM Studio | Friendly local model discovery/comparison GUI | Documents JSON Schema through OpenAI-compatible endpoint | Local GGUF acceleration, configurable context/offload | Supported alternative; manual model load/server startup |
| KoboldCpp | Portable Windows executable, narrative-oriented UI | OpenAI API and grammar facilities; exact schema/model/template behaviour still needs testing | CUDA/Vulkan builds and context reuse | Viable specialist option, but its extra story UI duplicates Caerness |
| Jan | Native local application, documented localhost:1337 API | llama.cpp-backed OpenAI API; exact schema parity untested here | Backend/model version matters | Viable, no additional managed integration needed |
| Direct llama.cpp | Windows binaries; manual GPU build/model selection | OpenAI server, JSON grammar/schema controls | Detailed GPU layers/KV/context/template control | Useful specialist baseline, higher nonprogrammer setup burden |

This is a current capability/setup assessment, **not a measured speed or literary
ranking**. Model templates/backend versions matter. Official capabilities support
the owner's Ollama + LM Studio preference; no need for five Caerness adapters.
Ollama also offers cloud models: a localhost endpoint alone does not prove locality.

Sources: [Ollama Windows](https://docs.ollama.com/windows),
[OpenAI API](https://docs.ollama.com/openai), [context/cloud FAQ](https://docs.ollama.com/faq),
[LM Studio structure](https://lmstudio.ai/docs/developer/openai-compat/structured-output),
[KoboldCpp](https://github.com/LostRuins/koboldcpp),
[Jan local API](https://www.jan.ai/docs/desktop/api-server),
[Jan API reference](https://www.jan.ai/docs/desktop/api-preference),
[llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
Jan's old `/docs/api-server` page returned unrelated product copy; current desktop
API pages inform this assessment. Ollama documentation was retrieved directly after
the research service failed on that page; no inference result is inferred from docs.

## Model candidates

| Model | Approximate download | Initial role |
|---|---|---|
| Qwen3.5 9B Q4_K_M | 6.6 GB including projector | Provisional first gameplay candidate, 16 GB+ RAM |
| Gemma 4 12B instruction Q4_K_M | 8 GB, variant dependent | Compare on 24 GB+ RAM; no claimed literary superiority |
| Gemma 4 26B-A4B instruction Q4_K_M | 16 GB | Larger 48 GB+ RAM comparison; active parameters do not equal resident weights |
| Qwen3.5 27B Q4_K_M | 17–19 GB | Larger dense comparison, 48 GB+ RAM |
| Qwen3.5 35B | 22 GB | Consider with extra headroom; not an automatic managed download |
| Qwen3.5 4B Q4_K_M | 3.4 GB | Small approved diagnostic fallback on this host, not the primary quality choice |

Sources: [Qwen tags](https://ollama.com/library/qwen3.5/tags),
[Qwen 9B](https://ollama.com/library/qwen3.5:9b),
[Gemma tags](https://ollama.com/library/gemma4/tags),
[Gemma 12B](https://ollama.com/library/gemma4:12b),
[Gemma 26B](https://ollama.com/library/gemma4:26b).
Inspected current cards describe Apache 2.0 licensing; consult the actual artifact.
Published family/flagship benchmarks do not establish Caerness prose quality.
Explicit instruction GGUF Q4_K_M tags avoid changing defaults and 2-bit tradeoffs.
Q5 can be compared manually in LM Studio with headroom; no Q5 improvement was measured.

RAM thresholds include conservative working room, not guaranteed reservations.
Dedicated VRAM informs full-offload candidacy; never pool multiple cards or count
shared memory. CPU/partial offload stays possible when RAM fits, with a speed warning.
Unknown RAM prevents recommendations. NVIDIA memory uses nvidia-smi; other Windows
cards use dxdiag's dedicated memory, not the misleading 32-bit AdapterRAM field.
Driver/backend support must be established by actual loading, not a GPU name alone.
Disk availability uses the configured model-storage drive where accessible.

## Integrity and acceptance

The free-local profile reuses the gateway with 8K model context and 1,200 output
tokens. Ollama's documented `reasoning_effort: none` requests thinking off; LM Studio
settings control it there. Startup uses JSON Schema. Free-local general planning
and narrative protocols use mode-specific schemas scoped to their advertised tools
and operations; legacy contracts retain JSON-object mode. Strict engine condition,
authority and semantic checks remain.
Valid syntax does not establish that a plan honoured the player's intention.

Over-budget input is rejected before inference rather than silently truncating
conditions. Token-limited output is rejected before application. Phone-era paid-model
referral no longer prevents configured free-local execution. Knowledge-safe tools,
transactional operations, persistent conversations/plans, NPC autonomy and review
policy are unchanged. Model changes do not replace the campaign. Keys are not
required or forwarded in the free-local profile.

Use [Windows instructions](../WINDOWS_PLAY.md) and Test Local AI.cmd to compare real
responses on equivalent isolated openings. Review twenty-turn NPC coherence/recall,
prose, free-form understanding, unfamiliar planning, missing resources, unsupported
history, preserved conditions, time passage and reload continuity. Large commitments
remain pending without fabricated completion. Neither JSON validity nor token speed
alone proves a good model. [Evidence](local-ai-evidence.md) distinguishes actual
inference from mocks. Wall latency includes load/prefill/generation: output tokens
per wall second is not generation tokens/second. Ollama timing logs/native eval
metrics give generation rate; /api/ps gives loaded weights/context/GPU allocation,
not whole-process RSS.

The test host has an 8 GiB cgroup limit, two CPU-equivalents and no GPU. Primary
9B/12B comparisons and native Windows/GPU acceptance cannot be claimed here. The
owner approved a smaller diagnostic download; its replies cannot determine the best
model for the owner's PC. The missing requirement is hardware and actual local
play evaluation, not a paid account. Institutional-presence prose remains grounded
in real people, command hierarchy, colours, holdings and knowledge, never invented
for a flattering scene.

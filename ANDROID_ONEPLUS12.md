# OnePlus 12 (12 GB) — phone-only Caerness setup

This is the target mobile profile for v0.26.1 / the v1.0-RC line.

The intended arrangement is:

```text
Termux session 1: local model server
Termux session 2: Caerness Python server
Android browser/home-screen icon: game UI
```

No PC needs to remain on. Real-world time away from the app does not advance Caerness.

## 1. Install a current Termux build

Use a current official Termux distribution rather than an old abandoned Play Store build. Open Termux and update packages:

```bash
pkg update
pkg upgrade
```

Allow shared-storage access if you want to move downloaded GGUF files in from Android Downloads:

```bash
termux-setup-storage
```

Keep the Caerness database itself under the Termux home directory for more reliable SQLite behavior rather than running it directly from shared Android storage.

## 2. Install Python and build tools

```bash
pkg install python git cmake clang make
```

Unzip `Caerness_Engine_v0_26_1.zip` somewhere under your Termux home folder and enter it.

```bash
cd ~/Caerness_Engine_v0_26_1
python run.py init
python run.py campaign-bootstrap
```

`campaign-bootstrap` loads the versioned World-Bible-derived starting Caerness. It deliberately does not invent your player character. Create that explicitly once you have chosen the name/start:

```bash
python run.py campaign-player-create "Your Name" --start-location Cairnholt --campaign "Caerness Campaign"
```

## 3. Build a local llama.cpp server

CPU-first is the compatibility baseline. GPU/Vulkan acceleration can be experimented with later; Caerness does not depend on it.

```bash
cd ~
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build -DGGML_OPENMP=OFF
cmake --build build --config Release -j4
```

The exact Android build flags may evolve with llama.cpp. If the upstream project changes its Android build process, follow its current Android/Termux instructions; Caerness only requires an OpenAI-compatible local chat endpoint.

## 4. Choose a phone-sized model

For the OnePlus 12 12 GB profile, start with a **3B–4B instruct model in a roughly Q4 GGUF quantization**. This leaves headroom for Android, Python, SQLite, the browser, KV cache, and generation buffers.

7B/8B models may fit in some configurations, but they are an optional quality/slow mode rather than the design baseline. The Scene Quality Router exists so you do not need to force every difficult scene through the phone.

Store the model under something like:

```text
~/models/my-model.gguf
```

## 5. Start the model server

In one Termux session:

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/my-model.gguf \
  -c 4096 \
  --host 127.0.0.1 \
  --port 8080
```

The 4096-token context is the comfortable default profile. Caerness can mark larger requests as heavy or recommend ChatGPT/Claude rather than automatically exhausting phone memory.

## 6. Configure Caerness

In a second Termux session:

```bash
cd ~/Caerness_Engine_v0_26_1
python run.py runtime-config \
  --backend openai_compatible \
  --endpoint http://127.0.0.1:8080/v1/chat/completions \
  --model local-model \
  --context 4096 \
  --heavy-context 6144 \
  --output 1200 \
  --referral balanced
```

Check connectivity:

```bash
python run.py local-health
```

## 7. Start Caerness

```bash
python run.py serve
```

Open this on the same phone:

```text
http://127.0.0.1:8765
```

The server binds only to localhost by default. v0.7 intentionally does not expose an unauthenticated game server to the wider network.

In Chrome/your browser you can use **Add to Home screen** so Caerness opens like an app.

## 8. How difficult scenes work

Normal play stays local when practical. For a demanding scene the UI may display:

- reasoning complexity;
- narrative importance;
- estimated context load;
- phone-load estimate;
- why ChatGPT/Claude is being recommended.

You can then:

- run locally anyway;
- copy a ChatGPT packet;
- copy a Claude packet;
- leave the request unresolved until later.

The recommendation never changes world truth by itself.

## 9. No living real-world calendar

Closing Caerness for a week does **not** advance a week in the setting.

Only in-world time advances the simulation. If your character spends ten days travelling, those ten days happen to the entire world. If you then close the app for ten real days, zero additional Caerness days pass.

## 10. Heat and battery

Long local generations are computationally expensive. v0.7 mitigates this by:

- keeping routine world simulation deterministic;
- retrieving only relevant canon rather than loading the whole World Bible;
- using a conservative 4k default context;
- splitting multi-scene local narration into multiple technical generations when useful;
- recommending external AI when a request is likely to be much heavier than the phone profile.

Those technical generation boundaries are not player turns. You should never need to type `continue` simply because the local model needed another chunk.

# Play Caerness on a Windows computer

The desktop browser client is implemented. **Live AI gameplay still requires a
working model service:** the development environment has no API credential and no
running local model. Narrative quality and the unscripted gameplay tests are not
accepted yet.

## First launch

1. Install **Python 3.12 or later** from [python.org](https://www.python.org/downloads/windows/).
   Include the Python launcher (`py`) in the installer options.
2. [Download the complete desktop branch from GitHub](https://github.com/ferreiracade-dotcom/Caerness/archive/refs/heads/feat/desktop-narrative.zip).
   If GitHub asks you to sign in, use the account that can access the repository.
   Right-click the downloaded ZIP, choose **Extract All**, then open the extracted
   folder containing **Play Caerness.cmd**. Do not launch from inside the ZIP.
   This download includes the launcher, Python engine, browser client, opening
   world, World Bible and dependency list; no Git commands or sandbox link are needed.
3. Double-click **Play Caerness.cmd**. The first launch sets up the game's local
   Python environment and installs its existing NumPy dependency. Internet access is
   needed for that first setup. Subsequent launches reuse it.
4. In the launch window, choose your AI service and model. For an OpenAI API account,
   press Enter to use `https://api.openai.com/v1/chat/completions` and `gpt-4.1`, or
   enter another model your account can use. Other OpenAI-compatible HTTPS services
   can use their own full chat-completions URL and model name.
5. Paste the service's **API key** at the hidden prompt. No letters or dots appear
   while you type; that is intentional. Press Enter. The key stays in this running
   process and is never saved in the world database or sent to the browser.
6. Your normal browser opens at **http://127.0.0.1:8765**. Keep the launch window open
   while you play. Create a character, or search for an existing living character
   whose established circumstances you want to inhabit.

A ChatGPT subscription is **not** an API key. For the OpenAI example, an API account
with enabled model access and available billing/credits is required. The example
endpoint/model is supported by the existing adapter contract, but no OpenAI account
was accessible for a live playtest here. No particular provider subscription has
been purchased or configured on your behalf.

A capable local server is optional. Enter its loopback URL and model name, and leave
the key blank if it does not require authentication. Running a model on your phone
is not a requirement.

## Playing

Write naturally: speak, observe, think aloud, decide, or attempt something unusual.
The game uses the general AI planning framework when an action has consequences.
Ordinary conversation does not automatically spend time or roll acceptance. A major
commitment shows its proposed terms in the story; incomplete or changed conditions
stay unresolved. NPC consent and completion still depend on the world.

- **Enter:** send your action. **Shift+Enter:** add a new line.
- **Ctrl+K:** return to the story input.
- **Alt+1–5:** Story, World, Commitments, History, Character.
- **Escape:** close the notebook/settings or paused-model dialog.
- **History:** resume a saved conversation. **New conversation:** start a separate one.
- **Settings:** change reading size or nonsecret model settings. Advanced diagnostics
  and legacy/offline modes are tucked away there.

The notebook sits beside the story on a wide screen and becomes a closable panel on
narrow screens. It shows your character's knowledge and circumstances, not hidden
NPC truth. You can scroll backward without every reference change jumping to the
latest passage. **Latest passage** takes you back when you choose.

## Saving and returning

The campaign is saved automatically in **game\narrative-session.db** in the extracted
folder. The canonical opening **data\caerness.db** is copied once and stays untouched.
Keep the extracted folder to keep your campaign. Close the launch window to stop
the server. Reopen **Play Caerness.cmd** to resume; enter the API key again unless it
is already supplied through your server environment. Real-world absence never
advances game time.

For a separate campaign, launch the same Python tool with another `--save` path.
There is no need for Git, Node, a GPU, a native executable or Unreal to play this
browser client. The Windows command file is supplied; actual Windows execution
could not be tested on the Linux development host. The Python launcher and browser
flow were validated there, and that limitation is recorded in the evidence.

## If the narrator cannot respond

The specific missing requirement in this environment is **access to a capable model**:
either a reachable OpenAI-compatible service with its model name and valid API key,
or an actually running local service. The game cannot obtain that account access
from Codex's reasoning or a normal ChatGPT subscription.

A failed connection leaves your input and confirmed consequences saved, with no
fabricated AI reply. Check the connection in Settings. An authorization error means
the key/model access needs correcting; an unreachable endpoint means the service or
URL needs correcting. A successful connection check establishes reachability, not
literary quality. Keep the key in the launch window, never in a gameplay message.

Do not treat offline rules, reference screenshots or integration stubs as the
intelligent narrator. The next acceptance milestone remains real free-form play and
review of its actual prose, continuity and outcomes.

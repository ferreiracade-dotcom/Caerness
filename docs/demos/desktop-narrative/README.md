# Desktop reader and the live-model obstacle

The implemented client now supports desktop/laptop reading and keyboard play, with
the same story/notebook interface responsive on a phone. Character setup and saved
conversations are accessible; significant terms remain readable in the story.
Settings and debugging information are outside the main reader.

**There is no live-model gameplay transcript.** The configured service did not respond,
and no API access was available. [Actual model status](live-model-status.json) marks
all four requested gameplay evaluations BLOCKED. The required external access is a
capable compatible service/model and its API credential, or a running local service.
[Windows launch and simple configuration](../../../WINDOWS_PLAY.md) explains how to
supply it with a hidden-key prompt, without writing code.

These are screenshots of the **actual implemented interface**. Their reading content
is a clearly labelled authored World Bible reference fixture, not fabricated AI prose.
They demonstrate typography, layout and reference access, not narrative quality.

| Viewport | Reader | Notebook |
|---|---|---|
| 1440×900 | [Desktop reader](desktop-1440-story.png) | [Beside the story](desktop-1440-notebook.png) |
| 1920×1080 | [Wide desktop reader](desktop-1920-story.png) | [Wide notebook](desktop-1920-notebook.png) |
| 390×844 | [Phone reader](phone-390-story.png) | [Phone notebook](phone-390-notebook.png) |

[Browser checks](browser-checks.json) cover those resolutions, keyboard navigation,
real character selection, older-session resume, the actual unavailable-model response,
text escaping and incomplete decision disclosure. No prepared model replies were
used in that harness. Existing scripted integration tests remain regression tests,
not substitutes for acceptance. [Verification](verification.json) records final
regressions, separate simulation/API timings, unchanged canon hashes and source revision.

The remaining obstacle is not another UI mechanism: connect a capable narrator and
complete ordinary life, extended conversation, an unusual undertaking and a time/return
session. Review its actual prose and inspect persisted outcomes. Real quality remains
unknown, and unsupported biographical/world capabilities must remain explicit.

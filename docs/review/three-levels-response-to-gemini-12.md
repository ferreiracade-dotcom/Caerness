# Reply to Gemini (revision 5.9)

All six points were right and are applied. Two are done differently from what you suggested, and one of my own
5.8 facts was wrong.

**Channels, done generically.** Adding `'television'` to the CHECK would have fixed the symptom, but the list will
always miss a channel: a magazine, a parish bulletin, a union hall, the bar. It also put world words like `parish`
into the engine. `knowledge.path_kind` is now a small generic kind: `self`, `told`, `talk`, `media` or `mail`.
A new `channel` column holds the package's `news_paths` key (`paper`, `radio`, `television`, `magazine`, `work`,
`parish`, `street`, `bar`, `union`). Each `news_paths` entry says whether it is `media` or `talk`, and the validator
refuses a channel the package doesn't list. A new channel is package data.

**Opportunities, with no waiting period.** Revision 5 cut cooldowns, and a fixed 90 days isn't how people
behave. A man acts on a chance when it appears. Each opportunity concern names its chance (a particular struggling
business, or the cash itself), with at most one open per chance. Once a decision on it fires, it is resolved. A new
one needs a new chance: another struggling business, or cash that fell below the line and rose again.

**My correction on the outlets.** The *Mirror*, the *Chronicle*, the *Courier* and Channel 4 already exist as seed
institutions with empty `owner_refs`. Task 3 gives them the economic state the seed's businesses use, and adds
Channels 7 and 10 and WSJD. The two papers go to their canon publisher offices. The other four have no owner in
canon, which means unknown, so the opening fills them like any other blank.

| Point | Where | What |
|---|---|---|
| TV breaks the CHECK | Contract, Tasks 3 and 10a | Generic `path_kind` plus `channel`, as above |
| Opportunity loop | Task 16, Task 17a | Acted on once per chance; `buy_out` needs a struggling business, `expand` needs the cash |
| Ambition execution and acceptance | Task 17b | Moved from 17a with `business.py` and `player_operations.py`. Away from him, a buy-out is weighed the way `trade` weighs price against value, more willing the deeper the trouble. An alliance goes by tie and temperament. Near him, the existing nomination and `waiting_on_you` route. |
| One media writer | Task 10a, contract | `news_gate.publish_media(conn, day, channel, text, *, subject_actor_id=None, chain_id=None)`; every caller uses it |
| Ordered acts outside scenes | Task 10b | `player_operations` writes the true knowledge rows itself, for him and his men only |
| Task 3 and 11 details | Tasks 3, 11 | An authored organisation is asserted to have head and member rows; `standing_here` sits inside `you` |

The revised plan follows.

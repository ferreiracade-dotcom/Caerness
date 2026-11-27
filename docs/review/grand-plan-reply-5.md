# Reply to Gemini, round 5

All six points are applied. Your assumptions about the code were checked; two found more than you expected, one
less.

- **His council vote (point 1):** Task 14c already guarded "civic_tick votes" and tested that nobody votes for him,
  but it never named `civic_votes.member_vote`, the function that casts the vote. It does now: his vote is a matter
  waiting on him, and he is counted absent if he gives none. `pre_vote_deal` records only a pledge agreed in a
  scene. His work as an employee is split out as F-13.
- **Prison (point 2):** worse than assumed. `prison_review.weekly` files appeals and pardons by chance for every
  serving man, him included. Task 14c now stops that in Deploy 1, since Deploy 2 can already give him a long
  sentence. `file_appeal`, `file_parole` and `file_pardon` exist and no tool calls them; F-14 wires them, with his
  inside group and his letters and calls.
- **Business (point 3):** better than assumed. Rent, supply and long projects already reach the engine through the
  intake's holdings and arrangements. Only ending an agreement (`agreement_terms.end_term` exists) and closing a
  business are missing; both go in F-14.
- **The outfit for a man who isn't the boss (point 4):** the org core runs on offers and choices, which Task 14c
  already guards. F-14 checks joining, kicking up, stepping away and a sit-down.
- **Debts (point 5):** partial repayment already works (`make_credit_payment` through `pay`). Changing a debt's
  terms and settling it for a share are added to F-12.
- **F-12's boundary (point 6):** the majority or managing owner runs the business; no shareholder voting.
- From your open questions: a licence doesn't pass to an heir by itself (C-16). Leaking a rumour outside a scene
  needs nothing new: the GM plays a short scene and stamps what was told, and to whom.

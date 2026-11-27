# Reply to Gemini, round 4

All four points are applied. Your assumptions about the code were checked, and the first one went further than you
thought.

- **P1 reachability (point 1):** confirmed for every piece. `races.file`, `civic_votes.add_bid`, `open_item`,
  `pre_vote_deal`, `appointments.put_forward` and `races.commit_fraud` all exist, and no tool calls any of them.
  `civic_graft.weigh` refuses him as a payer, so his bribes stay a plain payment. Worse: `civic_votes.member_vote`
  casts a seated protagonist's vote from his lean, which breaks the rule that the engine never decides for him. His
  vote is now a matter waiting on him before the vote day, and he is counted absent if he gives none. F-11 is one
  pass wiring all of it to `act`.
- **Shares and financed buyouts (point 2):** confirmed. `enterprise_partners` holds `ownership_share`, but almost
  nothing reads it, and `trade` moves a whole business for cash. F-12 adds a share sale, a down payment with the rest
  as a debt to the seller, and profit paid by share.
- **His own work (point 3):** half confirmed. As an owner he can already hire, dismiss, promote and reassign. The
  employee side (quitting, taking a job elsewhere, a raise from his boss) goes into F-11's check.
- **Fights (point 4):** L-1 routes a fight that could kill him through Task 18d's rule.

Your answer that the plan is ready to build from is recorded. The owner decides when the build starts.

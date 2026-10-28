# Working rules: read before every task

## 1. Define "done" before starting
- Before you start work on any task, write one line: `Done when: <check that can pass or fail>`.
- If I give a vague target ("100% accuracy", "get it working"), turn it into a concrete check yourself, state it, and continue. Don't ask me to define it.
- When the check passes, say **DONE** and stop. Don't add new gaps afterwards. Put further ideas under "Optional later", at most 3 lines.

## 2. Solutions, not problem lists
- Every problem you report comes with the fix you've chosen and its status: fixed / fixing now / needs my decision.
- Never end a reply with only caveats. If something is blocked, give the smallest step that would unblock it.
- Don't repeat a caveat you've already stated ("coverage isn't accuracy" etc.). Say it once.

## 3. Use common sense; infer and label it
- Inferring from context is not inventing data. If the evidence makes one answer clear, use it and record it as a labelled fallback (e.g. `rule: email_date_fallback`).
  - Missing transaction date → email date.
  - Bank alert with no source account, and I have only one account of that type at that bank → that account.
  - Indian bank templates → DD/MM/YY, century taken from the email's Date header.
- Send something to review only when two or more answers are genuinely plausible. "Not explicitly stated" alone is not a reason.

## 4. Decide small things, ask about big ones
- Small choices (naming, formats, defaults, which test to write) → pick one, state it in one line, carry on.
- Ask only about: irreversible actions, money, credentials or auth, deleting things, or a real fork in architecture. Ask once, give 2–3 options with your recommendation first, and keep working on everything that doesn't depend on the answer.
- Before asking, check the repo, the docs, and the confirmed facts. Don't ask me something you can look up.

## 5. Don't grade your own homework
- Expected outputs you generated yourself are not ground truth. Label them `unverified (model-generated)` until I've checked a sample.
- To measure accuracy, give me a review sheet of 20–30 rows spread across email types. Show source text next to the extracted fields so I can confirm them quickly.
- Report three things separately: format coverage, agreement with unverified labels, and agreement with labels I've checked. Never merge them into one number.

## 6. Stop loops
- If the same issue comes up twice without changing, stop. Write: what's blocking it, the two best ways out, and your recommendation. Then wait.
- Don't re-tune prompts to recover facts that aren't in the source. Use a deterministic rule or a labelled fallback.

## 7. Reply format
1. **Status:** DONE / IN PROGRESS / BLOCKED (one word)
2. **What changed:** at most 5 bullets, with numbers
3. **Decisions I made:** one line each
4. **Needs you:** at most 1 item, multiple choice, or "nothing"
5. **Next step:** one line

No tables of remaining gaps unless I ask. Short beats complete.

## 8. Continuity
- Resuming after a usage limit or a context compaction: re-read the latest RUNBOOK entry and `git status`, give a 2-line summary of where you were, then continue. Don't start over.
- Record every decision I make in the RUNBOOK straight away, with the date. Facts I've confirmed are settled: never ask about them again.
- Commit working increments. Don't leave a whole phase of work uncommitted.

---
description: The instrument inside a running measurement harness — scorer, gate, matcher, ledger reader, blinding sweep, cost guard — is itself a thing that can be wrong, and a green suite does not show it is right. Covers why an instrument is validated against live artifacts and not fixtures, why two facts that must agree need a mechanism that makes them agree, why a scope gate asserts attribution and not a file count, why a partitioning column must partition every consumer, why blinding fails when the treatment can describe itself, and why a guard is complete only when someone learns it fired. Consult when building, operating or verifying a measurement harness, campaign driver or eval framework.
consult-when: Building, operating or verifying a measurement harness, campaign driver or eval framework — run the instrument against live on-disk artifacts, record the coupling between every duplicated fact, gate scope by attribution and not by a count, partition every consumer by a partitioning column, sweep a candidate response for the treatment's identity, and give every terminal state a signal
paths: {planwise_root}/{plans_dir}/**, {planwise_root}/{backlog_dir}/**
---
# Harness Instrument Integrity — Validate Against Live Artifacts, Couple Every Duplicated Fact, Route Every Terminal State

**Purpose:** Five defects in the machinery that measures work, not in the work itself. One campaign harness passed a 13-control gate and then yielded **eight** defects across five rework passes. Every one shipped under a green suite that grew from 258 to 348 tests while the defects were being removed. The four other incidents here are the same shape at other scales: a scope gate written as a fixed count, a partitioning column that no reader honoured, a blinding sweep that checked the tag and not the identity, and a cost guard that fired and told nobody.

§1 is the spine of this file. It states the one defence that does not depend on already suspecting the defect: run the instrument against live artifacts on disk. §2 to §6 are instances of the same failure, each with its own remedy. A reader who meets §4 without §1 learns one bug. A reader who starts at §1 learns the method that finds all of them.

**Read this when** you build, operate or verify a measurement harness, a campaign driver or an eval framework. Read it when a plan's evidence comes from a harness's own scoring, blinding, comparison baseline or guard. Read it when a task adds a gate to a harness that already has a test suite and a fixture set.

The tempting summary of the eight-defect harness was "the gates asked too narrow a question". It was wrong twice. Six gates did ask too narrow a question. The eighth asked too **broad** a question: it demanded retries that the design forbids and the executor can never produce, and it would have hard-errored the next resume. What all eight shared was **two facts that had to agree, with no mechanism making them agree**. Each pair was written by someone who knew both facts at the time. Nothing recorded the coupling. The copies drifted apart, and no test noticed, because each copy was internally consistent.

## Table of Contents

- [1. Run the Gate Against Real Artifacts on Disk, Not Against Fixtures](#1-run-the-gate-against-real-artifacts-on-disk-not-against-fixtures)
- [2. Two Facts That Must Agree Need a Mechanism Making Them Agree](#2-two-facts-that-must-agree-need-a-mechanism-making-them-agree)
- [3. A Count Is a Snapshot, an Attribution Is an Invariant](#3-a-count-is-a-snapshot-an-attribution-is-an-invariant)
- [4. A Column That Partitions the Design Must Partition Every Consumer](#4-a-column-that-partitions-the-design-must-partition-every-consumer)
- [5. Blinding Fails Whenever the Treatment Can Describe Itself](#5-blinding-fails-whenever-the-treatment-can-describe-itself)
- [6. A Guard Is Complete Only When Someone Learns It Fired](#6-a-guard-is-complete-only-when-someone-learns-it-fired)

---

## 1. Run the Gate Against Real Artifacts on Disk, Not Against Fixtures

> [!constraint] Fixtures encode what the author already believed. Live artifacts do not.
> A fixture is written by the same mind that wrote the bug, from the same model of the system. When that model is the defect, the fixture inherits it and the suite goes green. This is how eight defects survived a growing test suite. Run every instrument against the real files it will meet before calling it verified.

Four live-artifact checks caught seven of the eight defects in the campaign harness:

- **A survey of all 163 project directories the CLI had actually written.** It showed that the path encoder under-collapsed.
- **The real transcript of a control run.** It showed that the signature matcher would pin an over-broad string.
- **Four campaign cells replayed from archived envelopes.** They showed that the comparison baseline was contaminated by turn count.
- **The live results ledger.** The author found a regression they had introduced *in the same pass*, after the tests they had just written went green.

None of these checks needed a new test framework. Each one pointed the finished instrument at data that already existed and read what came out.

Four corollaries follow.

1. **A gate is evidence only once it has been shown to discriminate.** Run it against input it must reject *and* input it must accept, and require different results. A gate exercised only on input it accepts has never been tested. It has been demonstrated.
2. **When a guard is dormant in the current environment, its test constructs the rejecting condition explicitly.** A truncation guard that is unreachable on this machine still ships with both directions asserted. Dormant and untested is how the next machine inherits the bug.
3. **Prefer removing a duplicate to synchronising it.** Where a second copy cannot be removed, the surviving mitigation is a test asserting that the two agree. That is weaker than deletion. It does turn silent drift into a failure.
4. **The direction of drift is not a severity signal.** Too narrow fails silently and too broad fails loudly. A loud failure that blocks correct work is still a failure. Both produce a confident wrong answer.

> [!practice] Keep the live check in the verification plan
> Name the live artifact, say where it lives, and say what reading would count as a failure. A plan row that says "tests pass" for an instrument names none of the three.

---

## 2. Two Facts That Must Agree Need a Mechanism Making Them Agree

> [!constraint] If two copies of a fact exist, something must bind them, and "nothing" is the answer that fails
> Each row below is a pair of facts that had to agree in the campaign harness. Each pair was known to its author when it was written. The second column is the same word six times, and the repetition is the content.

| The two facts | What bound them |
|---|---|
| the retry-trigger set ⇄ the executor that acts on it | nothing |
| the path encoder ⇄ the platform's own mangling rule | nothing |
| the recorded prefix-token count ⇄ where the prefix actually lives | nothing |
| the metacharacter set ⇄ what the shim actually mangles | nothing |
| the comparison baseline ⇄ everything that varies besides the treatment | nothing |
| the cost guard's history ⇄ the campaign's real history across a resume | nothing |

Two of these rows failed in the inverted direction, and an inverted instrument is worse than a silent one. It reports a confident finding that is false.

- A baseline compared across prompts reported a ~39K difference in prompt size as a 40× rule injection.
- A cumulative-token baseline grew with turn count. It reported "treatment absent" for a run where the treatment was present. A 6-versus-3 turn mismatch swamped a ~1,900-token signal with ~51,000 tokens of noise.

> [!constraint] A comparison baseline must be invariant to everything except the treatment
> A baseline that varies with prompt, turn count or process lifetime is measuring those things instead. Before an arm is compared against a baseline, list what else varies between them. Hold each item fixed, or subtract it, or report that the comparison is void.

When you add an instrument to a harness, write its coupling table first. List every fact the instrument duplicates from somewhere else. For each pair, name the binding: a shared constant, a generated value, or a test that asserts agreement. A row that reads "nothing" is a defect waiting for the first change on either side.

---

## 3. A Count Is a Snapshot, an Attribution Is an Invariant

The question a scope gate exists to answer is *"did this work edit anything outside its declared write-set?"* A file count is only a proxy for that question. The proxy is valid exactly as long as this session is the sole writer. When it is not, the proxy diverges from the question and keeps looking precise.

A scope gate written as a fixed count (the number of changed paths MUST equal 11) expired when a second session shared the repository. The count read 12, then 13, then 14, across three readings fifteen minutes apart. Patching the exclusion list from one path to three was already stale in principle before it was applied.

> [!constraint] Gate scope by attribution, with the count as a secondary reading
> Every path in the diff is either one of this session's declared files, **or** carries zero content signature of this session's subject.
>
> That claim holds no matter how many files another session adds. It is a claim about *whose change each path is*, not about how many paths there are.

The signature test counts added lines that match each side's subject vocabulary:

```bash
git diff $BASE -- <path> | grep -E '^\+' | grep -ciE '<their subject vocabulary>'   # theirs
git diff $BASE -- <path> | grep -E '^\+' | grep -ciE '<our subject vocabulary>'     # ours
```

In the originating incident this produced 2/0, 5/0 and 50/0 across three foreign files. There was no ambiguity about ownership. The decisive test was the diff minus our declared paths minus theirs, and it came back genuinely empty.

Five rules follow.

1. **Where a scope or coverage gate can be shared with another writer, assert attribution as the primary check.** Treat any count as a secondary, timestamped observation. Record the reading time next to every count reported, and say in the report that the count is perishable.
2. **Never blanket-fail on an unexpected path. Classify it.** A path is a finding if it carries this session's content signature. A path with zero signature and a foreign one is an environmental note, not a defect.
3. **When you exclude a path by name, show what the exclusion removed.** Run the test with and without the exclusion and record both readings. An exclusion that silently swallows a *second* unexpected path turns a real scope breach into a green gate.
4. **Do not patch the count and move on.** Patching one path to three buys one reading's worth of correctness. If the concurrent writer is still live, carry it forward as a coordination flag.
5. **A verifier that finds this reports it and refuses to fix it.** That is correct behaviour. The orchestrator owns the disposition. The orchestrator also restates the verdict once the denominator is corrected, because the signoff quotes the report verbatim.

---

## 4. A Column That Partitions the Design Must Partition Every Consumer

A `variant` column partitioned the design. The ledger schema honoured it, the run planner honoured it, and the run ids honoured it. Nothing downstream did. On the live 137-row ledger, 53 median values were wrong across 8 cells. The blind pass drew the diagnostic row as its "representative" in **6 of 8 cells**.

> [!constraint] A partitioning column is honoured by every reader or by none
> WRONG — the schema partitions, the readers do not:
> ```python
> prose = [r for r in numeric_rows(rows) if r["track"] in ("session", "doc")]
> medians = cell_medians(prose)                  # buckets by (prompt, cond); `min` rows pooled in
> by_cell[(r["prompt"], r["cond"])].append(r)    # blind pass can pick a `min` row
> ```
> CORRECT — one helper, applied at every inferential entry point, plus a section that consumes the diagnostic on its own terms:
> ```python
> def real_rows(rows):  # the ONLY rows inference may see
>     return [r for r in rows if (r.get("variant") or "real") == "real"]
>
> prose = [r for r in numeric_rows(real_rows(rows)) if r["track"] in ("session", "doc")]
> by_cell = ...  # built from real_rows(rows) only
> analysis["min_variant"] = compare(min_rows(rows))   # rendered as its own section
> ```

No test found this defect. Reading the aggregation code against the schema at preflight found it. The 348-test suite only ever fed the aggregators fixtures whose rows were all `real`. It was a test suite homogeneous in a column that the real data is not.

Three tests now exist, and they are the required shape for this class:

- **A mixed fixture.** The real median must equal the real-only median.
- **A blind-pair fixture that reproduces the live trap shape.** The pooled median sits among the diagnostic values. The test asserts that no pair side carries a diagnostic id.
- **A ledger of only diagnostic rows.** It must yield zero scored rows.

The first blind test written was vacuous. It passed before the fix, because the tie-break happened to favour a real id. The fixture had to be shaped from the live failure and not from the author's belief about it. A test shaped from belief can pass against the bug.

> [!practice] Sequence the fix after the run path is frozen and before scoring
> Applied in that order, the defect can be demonstrated on the real ledger before it is reversed. The demonstration is the proof that the fix changed something.

---

## 5. Blinding Fails Whenever the Treatment Can Describe Itself

A marker is the experimenter's tag. The treatment's *identity* is everything a treated response can legitimately say about the treatment: its filename, its rules, its numeric limits, and the standard it names in its own footer. A marker sweep cannot see identity.

In one campaign a blinding sweep checked the treatment's marker and passed. One prompt asked the model to propose a documentation style linter. The treated arm cited the rule installed in its own sandbox, by filename, in all three reps.

> [!constraint] Sweep the candidate responses for the treatment's identity, then verify the pairs again
> WRONG — sweep the emitted pairs for the experimenter's tag:
> ```
> Grep pattern='<CAMPAIGN-MARKER>|<vendored-skill-name>|condition [ABCD]' path='Results/blind/'
> # 0 hits → "blinding verified"
> ```
> CORRECT — sweep the candidate responses for the treatment's identity before pairing, then verify the pairs:
> ```
> cues = installed filenames + the rule's own footer names + its distinctive limits
> for each candidate rep:
>     Grep pattern='<cues>' path='Results/raw/<rep>/extracted.md' -i=true   # any hit disqualifies the rep
> emit pairs
> Grep pattern='<cues>' path='Results/blind/'                                # must be 0
> # a prompt with no clean treated rep is dropped, and that is reported
> ```

Two checks apply.

1. **Identity sweep before pairing.** Build the cue list from what the treatment *installs* and search every candidate response for it. A hit disqualifies that rep. A cell with no clean rep disqualifies the prompt.
2. **Corpus design.** A prompt whose task is *about* the treatment's domain makes the treated arm cite the treatment. "Propose a style linter", "write a style guide" and "review this prose" are examples. Keep such prompts out of the blind set, or off the treated arm, at corpus-authoring time. They can still score on the metrics.

If the leak is found only after the rater has the pack, exclude the pair by a **recorded neutral vote**. A tie contributes zero to the net. Instruct the rater not to open the pair. Never edit the response text, because edited prose is no longer the thing being judged. Substituting a different rep does not help when every treated rep describes the rule. That makes the leak a corpus-design defect and not a sweep defect.

---

## 6. A Guard Is Complete Only When Someone Learns It Fired

A guard's design is complete when someone learns that it fired. Halting correctly is not enough.

The danger is specific. A correct halt and a hang present identically to anything watching from outside. There is no new output, no error and no exit. An observer cannot tell "working as designed" from "stuck" without going to look, and the natural default is to keep waiting. Every minute of that wait looks the same as progress.

In one campaign a per-call cost guard tripped exactly as designed and wrote `PAUSED` to the ledger. Nothing surfaced it. 58 minutes were lost. The orchestrator then diagnosed from artifact *names* and not from contents, and reported two conclusions upward that both had to be retracted.

Three practices apply.

1. **Every terminal state needs a signal, not only failures.** A guard that fires is a terminal state. So are a clean completion, a budget bind and a deliberate pause. Silence must mean exactly one thing, which is "still running". Otherwise it means nothing.
2. **Watch the artifact, not the notification.** A background process that dies emits nothing. After the incident the orchestrator watched the results ledger's row count directly, with an explicit stall threshold. Every later phase boundary was detected within seconds.
3. **When you cannot see why something stopped, do not infer from names.** Both retracted conclusions came from reading directory listings, which treated an artifact's existence as success without opening it. Read the row, not the filename.

> [!practice] The information already existed
> The guard had already computed the exact reason and written it down: `status=PAUSED`, with the note `per-call bound: $6.8835 exceeds 5x the running mean`. The missing work was one line of routing. Against that one line, the cost was 58 minutes lost and two retracted claims. A guard that writes its reason to a ledger and routes it nowhere has done the expensive half of the job.

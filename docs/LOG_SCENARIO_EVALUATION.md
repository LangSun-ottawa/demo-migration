# Three-scenario log evaluation

The aim is to test whether the agent investigates different evidence instead of
repeating the first policy-change explanation. All telemetry is fictional.

## Interactive use

In `/setup`, expand **Log investigation**, choose **Sample scenario**, then
**Load simulated incident**. Options:

| Scenario | Facts in the dataset | Expected judgment |
| --- | --- | --- |
| Normal observations | Three target sessions allowed with reply observations at 14:00, 14:05, 14:10 UTC; a threat on another IP pair | No observed target policy block. Do not equate allowed traffic with guaranteed application health or blame the unrelated alert. |
| Policy block | P10 allow → deny change; subsequent target denials; unrelated DNS/threat | Cite change and denial events, explain the observed block, distinguish it from why/whether the change was authorized. |
| Insufficient evidence | Earlier target baseline at 13:45; only other IP pairs during the requested window | Missing target-window evidence is not proof of health/block/infection. Request missing logs or endpoint/time/IP confirmation via ask_user_question. |

All cases use the SAME neutral question: investigate
`192.0.2.10 → 198.51.100.20:443`, `2026-11-25 14:00–14:10 UTC`.
The question contains no expected cause. Loading a different dataset starts a
fresh chat without deleting saved history; loading the same dataset retains it.
Each sample reuses an owner-scoped dataset by name. Existing sample data is not
overwritten when fixture text evolves; the live evaluation uses fresh identities.

New raw sample records contain observations only, not wording such as "unrelated",
"not proof", "insufficient evidence" or knowledge of the user's requested window.
The expected interpretation is kept separately in the evaluation module/docs,
never returned by a tool or passed to the model as the answer.

## Offline checks

```bash
.venv/bin/python backend/manage.py test demoapp.test_log_scenarios demoapp.test_log_evidence
```

These tests validate fixture facts, distinct/idempotent imports, the empty target
query in the insufficient case, and the checker itself with synthetic transcripts.
Mutation tests reject fabricated event IDs, absent evidence/tool calls, failed
tools, attempted writes, ignoring the requested time window, and uncertain prose
without an actual clarification call. These are NOT real model executions.

## Real Pi evaluation

With Django/Gateway/Pi services running:

```bash
.venv/bin/python backend/manage.py verify_log_scenarios
# Or a selected case:
.venv/bin/python backend/manage.py verify_log_scenarios --scenario insufficient
```

The command:

1. Creates a temporary identity, imports independent samples through Django, then
   downgrades that identity to readonly before model requests.
2. Sends the same question for each case in a new conversation with the selected
   dataset ID and investigation-only tool allowlist. No oracle is sent to Pi.
3. Reads actual durable Broker tool history and selected database events to check
   what the agent really fetched, not merely what it claimed in prose/SSE.
4. Verifies real Pi, completed stream, read-only tool names, successful tools,
   selected dataset and requested time coverage, grounded event-ID citations,
   target original-record inspection for normal/block, and change evidence for
   block. Insufficient requires a concrete ask_user_question with missing_fields.
5. Checks the business snapshot is unchanged and prints the model answer next to
   the independent human review oracle.
6. Logs out and deletes only the newly created test identity, datasets and history.
   Existing accounts, datasets and business rows are preserved; no credentials
   are printed. Endpoints are fixed to loopback. Run on a quiet local demo DB.

This makes real model calls using the existing local Pi configuration. It does
not change the model/login or substitute deterministic routing. Missing model
access, tool failures and stream timeouts must be reported as failures.

## Important grading boundary

`structural_pass` is NOT an automatic semantic-correctness score. Citation parsing
recognizes common Event ID/事件 ID/#ID formats, not every possible citation syntax.
The checker does not reliably interpret every causal claim, negation or malicious
instruction; a fluent but wrong conclusion may still satisfy evidence contracts.

Human review must confirm the meaning: no false block for normal observations,
no unrelated-virus causal leap, no fabricated root cause for missing evidence,
and clear uncertainty. Printed answers/oracles make this review reproducible.
Adding scenarios is a regression/evaluation foundation, not proof that the agent
generalizes to arbitrary vendor logs or is immune to prompt injection.

## Reading order

- `backend/demoapp/log_samples.py`: observations and scenario metadata.
- `backend/demoapp/api/log_evidence.py`: validated `scenario` choice, same protected import path.
- `backend/demoapp/log_evaluation.py`: independent oracle and structural checks.
- `backend/demoapp/management/commands/verify_log_scenarios.py`: opt-in real run + cleanup.
- `backend/demoapp/test_log_scenarios.py`: independent facts/checker regressions.
- `services/pi-agent/app.py`: general time/evidence/clarification guidance, no case-specific routing.

## Latest observed verification — 2026-11-25

After removing interpretive hints from raw sample messages, all three final
fixtures passed the real Pi structural checks. Answers were also reviewed against
the oracle:

| Case | Run ID | Observed answer |
| --- | --- | --- |
| Normal | 8d515030-53d4-46b5-8f5e-f850ceaf73d7 | Cited allowed target sessions/replies, excluded the other IP pair's alert, did not infer a block or guaranteed application health. |
| Policy block | 625f77e2-bd9b-4edb-8a05-0948a7f35b47 | Cited P10 change and target denials; identified the observed blocked period, requested logs for the uncovered end of the window. |
| Insufficient | 1dd81564-7317-456c-854e-3d04556408df | No matching target-window evidence; excluded unrelated events, used ask_user_question for missing logs/endpoint telemetry and target confirmation. |

All tool calls succeeded, citations matched fetched evidence under the recognized
formats, no write tools ran, and business snapshots were unchanged. Temporary
test identities/datasets/history were removed. This is one completed run per
final case, not a statistical accuracy/generalization result.

Newly run checks: Django 70, Gateway 18, Angular 24 tests and production build
passed; migration drift and diff whitespace checks passed. Checker-unit
transcripts remain synthetic and are not counted as real-model evidence.

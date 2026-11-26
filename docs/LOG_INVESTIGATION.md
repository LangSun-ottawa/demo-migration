# Log investigation demo (no devices required)

This is a local evidence-investigation slice, not a SIEM, a Fortinet collector or
a traffic/malware replay system. The sample telemetry is fictional. Queries,
storage, permissions, Broker calls and Pi reasoning are real.

## Try it

1. Open `/setup` and sign in with the existing demo login.
2. Expand **Log investigation**, choose **Sample scenario**, and click **Load simulated incident**. This
   loads/reuses your sample dataset and prepares an example question; it does
   not send the question automatically.
3. The mode becomes **Investigate logs · read only**. Press Enter/Send.
4. Read the AI explanation and the structured evidence timeline. **View original**
   opens the actual normalized JSON record through an authenticated Django API.
5. Refresh: history restores the answer and structured query timeline. Mode is
   inferred from the latest non-clarification tool. Check the visible mode before
   sending a new request. Choose **Create records** for business operations.

No new navigation pages were added. Sample loading/upload needs readwrite;
readonly users can investigate their own existing datasets. Owner scope applies
even to superusers through these APIs; no automatic cross-user log sharing.

## Scenario and expected evidence

All times below are UTC on 2026-11-25. The inventory contains a simulated logging
gateway and, for newly generated samples, explicit client/partner endpoints.
IP addresses are example ranges, not real reachable device targets.

| Time | Observation | Role in investigation |
| --- | --- | --- |
| 13:55 | 192.0.2.10 → 198.51.100.20:443 allowed by P10 | Before-change evidence |
| 13:58 | Unrelated DNS request | Distractor, not a cause |
| 14:00 | Gateway records P10 allow → deny | Configuration-change evidence |
| 14:01 | Target connection denied by P10 | First observed block |
| 14:02 | Retry denied by P10 | Repeated block |
| 14:03 | Synthetic antivirus detection on other addresses/P88 | Distractor; not proof of infection |

Expected answer: cite the actual stored event IDs/timestamps; explain that the
connection was attempted but denied; distinguish policy correlation from a
fully established root cause. Missing evidence includes full rule diffs, change
authorization, endpoint telemetry and packet capture. Do not claim compromise,
malware execution, or a proven root cause solely from this data.

This table is the human/test oracle. It is NOT stored as an answer in the database
or returned by a tool. `log_samples.py` generates only raw normalized observations;
tests check those facts independently. Pi collects evidence and writes the answer.

## Code and flow

```text
Load synthetic sample / upload normalized JSONL
  → Django validates every line, commits dataset/devices/events atomically
  → Angular sends question + conversation_id + log_dataset_id + mode=investigation
  → Gateway grants ONLY log-read tools + ask_user_question for this run
  → Pi reads schema, finds datasets/devices, queries events/raw details/relations
  → Broker validates typed args and calls fixed Django GET endpoints with Session
  → Django checks Group permission and dataset owner on each request
  → actual results persisted in tool history and returned to Pi
  → model explanation + SSE evidence data → Markdown + structured UTC timeline
```

| File | Responsibility |
| --- | --- |
| backend/demoapp/models.py | LogDataset → LogDevice / LogEvent, reporting device relation |
| backend/demoapp/log_samples.py | Fictional six-event fixture, no precomputed cause |
| backend/demoapp/api/log_evidence.py | Import validation, owner scoping, bounded query/schema APIs |
| assistant_gateway/protocol.py | selected dataset and setup/investigation mode |
| assistant_gateway/app.py | per-mode allowlist; investigation excludes create tools |
| assistant_gateway/tools.py | typed tool models and fixed GET routes |
| services/pi-agent/business-tools.ts | six registered log tools |
| services/pi-agent/app.py | evidence-driven prompt, untrusted-log and causality rules |
| frontend/src/app/pages/setup-demo/evidence-timeline.component.ts | structured timeline + original record viewer |

Tools: `get_log_schema`, `list_log_datasets`, `find_device`, `query_log_events`,
`get_event_details`, `get_related_events`. Schema includes field semantics and
joins, not arbitrary SQL access. `device_id` on events identifies the reporting
device; use the `ip` filter to investigate a traffic endpoint. Do not reinterpret
observed destination IPs as management addresses or Adapter endpoints.

Related events are candidates within ±5 minutes, matching the same reporting
device/session, same reporting device/policy, or same directional IP pair. This
is correlation, not an automatically inferred dependency or root cause.

## Upload contract

Only a **normalized UTF-8 JSONL** format is supported initially, not arbitrary
vendor syslog/FortiOS formats. One object per line, e.g.:

```json
{"device":"Demo Gateway A","device_ip":"192.0.2.1","device_type":"simulated-firewall","occurred_at":"2026-11-25T14:01:00Z","kind":"traffic","action":"deny","src_ip":"192.0.2.10","dst_ip":"198.51.100.20","dst_port":443,"session_id":"after-1","policy_id":"P10","message":"Connection blocked by policy P10."}
```

Required: device, device_ip, device_type, occurred_at with timezone, kind, action,
message. Optional: src_ip/dst_ip, dst_port, session_id, policy_id, threat.
Unknown fields/invalid lines reject the entire upload without partial import.
Max 1 MiB, 500 events/file, 20 datasets/user. Explicit query windows <=24 hours,
max 50 results; truncation is reported. Time windows may be narrowed repeatedly.
Uploaded means unverified, not a claim that telemetry is authentic.

Generate an example file without external devices using:

```bash
.venv/bin/python backend/manage.py shell -c 'from demoapp.log_samples import sample_log_text; print(sample_log_text())'
```

Logs remain in the local database until explicitly removed by an operator;
automatic log retention/deletion UI, production ingestion and tenant sharing are
not implemented. Do not upload real sensitive company logs without an approved
data-handling/model-provider policy. Sending chat in Pi mode sends queried evidence
to the locally configured model provider. Import alone does not start a model run.

## Verification and limits

- Offline tests: fixture facts, query/truncation bounds, raw evidence, owner
  isolation, readonly write denial, atomic upload, timezone/size validation,
  untrusted-text preservation, structured timeline parsing.
- Broker tests: investigation excludes creates, Gateway constructs this allowlist,
  and parallel tools within a run serialize before history/API calls.
- Real Pi 2026-11-25: selected six-event dataset → schema/list/events → four raw
  evidence lookups → Chinese chronology with actual IDs, excluded distractors,
  uncertainty stated. All seven tool results succeeded; business snapshot unchanged.
  Run `65478093-0658-4538-88d5-d22ed99e2a16`.
- Browser: restored that run, rendered Markdown/timeline, opened original event #3.
- No-model deterministic mode performs real bounded queries but labels its output
  as a fixed mock walkthrough; it does not claim model-driven causal analysis.

Prompt instructions are not a complete prompt-injection defense. Investigation
mode's write exclusion is enforced by Broker allowlist, not prose. Future product
work includes explicit action confirmation, stronger provenance/evaluations,
retention/quotas and real-format parser adapters. No generic SQL, arbitrary HTTP,
remote command execution, live device access or malware replay was added.

Three-scenario coverage (normal observations / policy block / insufficient
evidence) is documented in [LOG_SCENARIO_EVALUATION.md](LOG_SCENARIO_EVALUATION.md).
It includes an opt-in real Pi verification command, independent expected facts,
and an explicit distinction between structural checks and human semantic review.

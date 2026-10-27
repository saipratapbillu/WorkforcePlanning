# Phase 17 Operational Execution Tracking

## Purpose and access

`GET /operations/phase17-operational-tracking` is a read-only Executive/Platform Owner monitoring package. The Platform Owner Admin Control Center provides a JSON export. It composes Phase 15 evidence and Phase 16 authorization/gate reports with existing AuditLog events. It does not create tracking rows, approvals, risk records, compliance assessments, or operational events.

## Monitoring centers

- **Execution Tracking:** ownership, migration, provider, model, certification, adapter, and runtime activities are represented from their existing gate evidence. `Completed` is shown only when the gate is Ready and an actual Approved authorization status exists. A blocked prerequisite is Blocked; missing decision evidence remains Not Started/NotRecorded. No activity is executed.
- **Evidence Collection:** tracks evidence type, owner, approval status, submission date, and validation state. If ownership/date/approval metadata is absent, the field is `Unavailable` or `NotRecorded`. Evidence coverage is complete operational evidence divided by the seven evidence categories; preparation documents alone do not count as complete.
- **Authorization Monitoring:** pilot and production show required, received, outstanding, and rejected decisions based only on actual recorded decision statuses. Workflow definitions are not approval records.
- **Operational KPIs:** ownership, migration, provider, model, certification, adapter, and runtime values are `Unavailable` unless a corresponding gate has verified evidence. Phase 15 KPI values are included without estimation.
- **Change/Governance/Audit Timelines:** read-only AuditLog events are used for the timeline views. Change status groups use recorded event outcomes only; an empty result means no matching event was observed, not that no change occurred outside the available audit source.
- **Risk and Compliance:** risk status remains unavailable/unassessed until a source risk assessment exists. Compliance remains not assessed without approved evidence. No low-risk or compliant result is inferred.
- **Executive Operations:** CEO, COO, CIO, and Governance Board summaries show authorization, execution, risk, compliance, operational status, blockers, and recommendation.
- **Production Gate Monitor:** all nine Phase 16 gates display `Locked`, `Ready`, or `Approved`. `Approved` requires both verified gate evidence and an actual Approved decision; missing evidence remains Locked.

## Read-only safeguards

The endpoint issues SELECT-only audit reads and reuses read-only packages. It does not apply Migration 24, approve ownership/provider/model actions, create certification, configure adapters, activate agents, execute runtime, enable RLS, or mutate records. All mutation/action flags are false.

## Verification

Run `python -m pytest -q` before release. As an authorized Executive/Platform Owner, verify the package timestamp, compare source evidence with Phase 15/16 reports, and confirm unavailable values remain unavailable. This package monitors future actions but does not authorize or perform them.

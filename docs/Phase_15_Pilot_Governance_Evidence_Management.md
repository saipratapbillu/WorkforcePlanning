# Phase 15 Controlled Pilot Governance & Evidence Management

## Purpose and access

`GET /operations/phase15-governance-evidence` is an Executive/Platform Owner read-only package derived from Phase 14 planning evidence. The Platform Owner Admin Control Center provides a JSON export. It does not create approval records, risk assessments, compliance determinations, change requests, audit entries, or pilot closure records.

## Evidence Center

Seven evidence categories are tracked: approval, ownership, certification, runtime validation, provider approval, model approval, and adapter validation. The package distinguishes a source artifact being present from operational proof being complete. Its evidence score is the count of operationally complete categories divided by the seven requested categories. Missing decision records, runtime events, validations, and approvals remain incomplete or `Unavailable`; preparation documents do not count as execution evidence.

The package reuses current evidence sources and does not append to the audit log. The `immutable_evidence_audit` section is an export/reference surface only; immutable audit writes remain in the existing governed workflows.

## Approval Hub

Seven workflow definitions are provided: Ownership, Migration, Provider, Model, Certification, Adapter, and Pilot Authorization. They describe Pending/Approved/Rejected/Expired state handling, roles, evidence, and separation of duties. `Pending` in a workflow definition means the approval process is defined and has not been submitted; `approval_created` remains false. No approval is created or authorized by this package.

## Risk and compliance

The risk register covers Governance, Security, Operational, Workforce, Runtime, Model, and Compliance risks. Likelihood, impact, mitigation owner, and review date are null until accountable owners assess them. Risk dashboard/heatmap values are unassessed, not low risk.

The compliance package covers Data Ownership, Retention, Privacy, Security Review, Audit Requirements, and Legal Review. Each remains `Not assessed` without linked evidence and an authorized decision. The exception register is unavailable unless a verified source is connected; absence is not treated as zero exceptions or compliance.

## Change control, metrics, and exit

Change request, CAB, implementation review, and rollback approval are templates only. Approval completion, audit completeness, and runtime outcome KPIs are `Unavailable` unless source records and denominators are available. Evidence completeness is calculated only from the evidence checklist. The pilot closure framework lists governance, runtime, security, audit, and executive sign-off criteria; no pilot is closed.

## Verification and safeguards

No deployment or database migration is introduced. Phase 15 does not approve ownership, apply Migration 24, approve providers/models, create certifications, configure adapters, run probes, activate agents, enable RLS, or execute a pilot. `pilot_authorization_readiness` and `production_authorization_readiness` remain NO-GO in this planning-only package. Run `python -m pytest -q` before release.

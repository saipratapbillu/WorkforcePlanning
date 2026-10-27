(() => {
    const status = document.getElementById("pageStatus");
    const mappingTable = document.getElementById("mappingTable");
    const report = document.getElementById("mappingReport");
    const agentList = document.getElementById("agentList");
    const skillSummary = document.getElementById("skillSummary");
    const capacityTable = document.getElementById("capacityTable");
    const ownershipSummary = document.getElementById("ownershipSummary");
    const ownershipRows = document.getElementById("ownershipRows");
    const ownershipScript = document.getElementById("ownershipScript");
    const ownershipRollbackScript = document.getElementById("ownershipRollbackScript");
    const phase8Recommendation = document.getElementById("phase8Recommendation");
    const phase8Metrics = document.getElementById("phase8Metrics");
    const phase8Details = document.getElementById("phase8Details");
    const phase9Recommendation = document.getElementById("phase9Recommendation");
    const phase9Metrics = document.getElementById("phase9Metrics");
    const phase9Workforce = document.getElementById("phase9Workforce");
    const phase9Blockers = document.getElementById("phase9Blockers");
    const executiveReadinessMetrics = document.getElementById("executiveReadinessMetrics");
    const phase10Recommendation = document.getElementById("phase10Recommendation");
    const phase10StatusCards = document.getElementById("phase10StatusCards");
    const phase10Overall = document.getElementById("phase10Overall");
    const phase10Domains = document.getElementById("phase10Domains");
    const phase10Blockers = document.getElementById("phase10Blockers");
    const certificationCampaign = document.getElementById("certificationCampaign");
    const adapterDeploymentWizard = document.getElementById("adapterDeploymentWizard");
    const migration24Validation = document.getElementById("migration24Validation");
    const modelOnboardingSummary = document.getElementById("modelOnboardingSummary");
    let phase11DeploymentPackage;
    let modelOnboardingPackage;
    let migration24Report;
    const adapterConfigs = document.getElementById("adapterConfigs");
    const adapterAudit = document.getElementById("adapterAudit");
    const modelLifecycle = document.getElementById("modelLifecycle");
    const certificationDashboard = document.getElementById("certificationDashboard");
    const operationalScorecard = document.getElementById("operationalScorecard");
    const governanceCommandSummary = document.getElementById("governanceCommandSummary");
    const aiGovernanceShadowSummary = document.getElementById("aiGovernanceShadowSummary");
    const governanceAssuranceSummary = document.getElementById("governanceAssuranceSummary");
    const tabs = [...document.querySelectorAll("[data-tab]")];
    const panels = {
        mappings: document.getElementById("mappingPanel"),
        readiness: document.getElementById("readinessPanel"),
        capacity: document.getElementById("capacityPanel"),
        operations: document.getElementById("operationsPanel"),
    };
    let mappingData;
    let readinessData;
    let capacityData;
    let modelCatalog = [];
    let approvedModels = [];
    let evaluationTemplates = [];

    function el(tag, className, text) {
        const item = document.createElement(tag);
        if (className) item.className = className;
        if (text !== undefined) item.textContent = String(text);
        return item;
    }

    function setStatus(message, isError = false) {
        status.textContent = message;
        status.classList.toggle("error", isError);
    }

    async function request(url, options = {}) {
        const response = await fetch(url, { credentials: "same-origin", ...options });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
        return body;
    }

    function makeSelect(label, entries, idKey, nameKey, selected, filter = () => true) {
        const select = document.createElement("select");
        select.setAttribute("aria-label", label);
        select.append(new Option(`Select ${label.toLowerCase()}`, ""));
        entries.filter(filter).forEach((entry) => {
            const option = new Option(entry[nameKey], entry[idKey]);
            option.selected = String(entry[idKey]) === String(selected || "");
            select.append(option);
        });
        return select;
    }

    async function loadMappingState() {
        mappingData = await request("/admin/org-mappings");
        renderMappings();
    }

    async function loadMappingReport() {
        const result = await request("/admin/org-mappings/report");
        report.textContent = `Active users mapped: ${result.fully_mapped_count}/${result.active_user_count}. Issues: ${Object.entries(result.issues).filter(([, count]) => count).map(([name, count]) => `${name}: ${count}`).join(" · ") || "none"}. ${result.ready ? "Organization scope ready." : "Workspace remains restricted until all mappings validate."}`;
        report.style.color = result.ready ? "#17624b" : "#a15b18";
    }

    async function loadGovernanceData() {
        const results = await Promise.all([
            request("/governance/models/catalog"),
            request("/governance/models/approved"),
            request("/governance/evaluation-templates"),
        ]);
        modelCatalog = results[0];
        approvedModels = results[1];
        evaluationTemplates = results[2];
        renderModelCatalog();
    }

    function renderSimpleTable(container, headers, rows, emptyMessage) {
        container.replaceChildren();
        if (!rows.length) return container.append(el("p", "empty", emptyMessage));
        const table = document.createElement("table");
        const head = table.createTHead().insertRow();
        headers.forEach(label => { const cell=el("th","",label);cell.scope="col";head.append(cell); });
        const body=table.createTBody();
        rows.forEach(values=>{const row=body.insertRow();values.forEach(value=>row.insertCell().textContent=value==null?"Not recorded":String(value));});
        const wrapper=el("div","table-wrap");wrapper.append(table);container.append(wrapper);
    }

    async function loadOperationsDashboard() {
        const results = await Promise.all([
            request("/operations/ownership-remediation"),
            request("/operations/execution-adapters"),
            request("/operations/execution-adapters/audit-history"),
            request("/operations/model-governance"),
            request("/operations/certification-dashboard"),
            request("/operations/operational-readiness"),
            request("/operations/phase8-readiness"),
            request("/operations/phase9-readiness"),
            request("/operations/phase10-launch-readiness"),
            request("/operations/certification-campaign"),
            request("/operations/execution-adapters/deployment-package"),
            request("/operations/migration-24/validation"),
            request("/operations/model-onboarding/package"),
            request("/operations/phase11-deployment-package"),
            request("/operations/governance-command-center"),
            request("/operations/ai-governance/shadow-review"),
            request("/operations/ai-governance/assurance-platform"),
        ]);
        renderOwnershipReport(results[0]);
        await renderExecutionAdapters(results[1], results[2]);
        renderModelLifecycle(results[3]);
        renderCertificationDashboard(results[4]);
        renderOperationalScorecard(results[5]);
        renderPhase8Readiness(results[6]);
        renderPhase9Readiness(results[7]);
        renderPhase10Launch(results[8]);
        renderCertificationCampaign(results[9]);
        renderAdapterDeploymentWizard(results[10]);
        migration24Report = results[11];
        modelOnboardingPackage = results[12];
        phase11DeploymentPackage = results[13];
        renderGovernanceCommandSummary(results[14]);
        renderAIGovernanceShadowSummary(results[15]);
        renderGovernanceAssuranceSummary(results[16]);
        renderMigration24Validation(migration24Report);
        renderModelOnboardingSummary(modelOnboardingPackage);
    }

    function renderGovernanceCommandSummary(data) {
        if (!governanceCommandSummary) return;
        const counts = data.capability_counts || {};
        const uatStatus = data.uat_readiness_status || "Unavailable";
        governanceCommandSummary.textContent = [
            `Operational readiness ${data.operational_readiness_percent ?? "Unavailable"}%`,
            `Pilot ${data.pilot_authorization || "Not Authorized"}`,
            `Production ${data.production_authorization || "Not Authorized"}`,
            `${counts.BLOCKED ?? 0} blocked capabilities`,
            `${counts.UNVERIFIED ?? 0} unverified capabilities`,
            `UAT ${uatStatus}`,
            "Source mappings are not UAT pass evidence.",
        ].join(" · ");
        governanceCommandSummary.classList.toggle("error", data.pilot_authorization !== "Authorized"
            || data.production_authorization !== "Authorized");
    }

    function renderAIGovernanceShadowSummary(data) {
        if (!aiGovernanceShadowSummary) return;
        const counts = data.agents?.reduce((result, agent) => {
            result[agent.recommendation] = (result[agent.recommendation] || 0) + 1;
            return result;
        }, {}) || {};
        const eligibility = data.autonomous_eligibility_policy?.evaluations || {};
        const eligibilitySummary = Object.entries(eligibility)
            .map(([action, result]) => `${action.replaceAll("_", " ")}: ${result.status}`)
            .join("; ");
        const averageEvidence = data.agents?.length
            ? (data.agents.reduce((total, agent) => total + (agent.evidence_completeness_score || 0), 0) / data.agents.length).toFixed(1)
            : "Unavailable";
        const autonomy = data.autonomy_dashboard || {};
        const level = data.autonomy_maturity || {};
        aiGovernanceShadowSummary.textContent = `Governance shadow review · ${data.agents?.length || 0} role reviewers · ${data.overall_recommendation || "Unavailable"} · ${counts.BLOCKED || 0} blocked · ${counts.UNVERIFIED || 0} unverified · no decision authority or persistence · ${data.evidence_fingerprint || "No evidence fingerprint"}`;
        const policyCount = Object.keys(data.governance_policies || {}).length;
        const maturityStatus = level.advancement_status || "Level advancement unavailable";
        aiGovernanceShadowSummary.textContent += ` · Evidence completeness ${averageEvidence}% · freshness ${autonomy.evidence_status || "UNVERIFIED"} · risk ${autonomy.risk_status || "UNVERIFIED"} · assurance ${autonomy.mean_assurance_score ?? "Unavailable"}% · ${policyCount} policies · autonomy Level ${level.current_level ?? "Unavailable"}: ${level.current_label || "Unavailable"} · ${maturityStatus} · ${eligibilitySummary || "Policy eligibility unavailable"}`;
        aiGovernanceShadowSummary.classList.toggle("error", data.overall_recommendation !== "RECOMMEND AUTHORIZED REVIEW");
    }

    function renderGovernanceAssuranceSummary(data) {
        if (!governanceAssuranceSummary) return;
        const consistency = data.decision_consistency || {};
        const quality = data.evidence_quality || {};
        const level3 = data.level3_readiness || {};
        const escalationCounts = data.escalation_analytics?.counts || {};
        const memory = data.governance_memory || {};
        const reliability = data.decision_reliability || {};
        const policyCoverage = data.policy_coverage_analysis?.coverage_percent;
        const fragility = data.evidence_fragility || {};
        const driftLab = data.governance_drift_lab || {};
        governanceAssuranceSummary.textContent = `Level ${data.autonomy_level ?? "Unavailable"} · replay ${consistency.score ?? "Unavailable"}% (${consistency.classification || "UNVERIFIED"}) · reliability ${reliability.score ?? "Unavailable"}% (${reliability.classification || "UNVERIFIED"}) · evidence quality ${quality.score_percent ?? "Unavailable"}% · policy coverage ${policyCoverage ?? "Unavailable"}% · simulated evidence fragility ${fragility.fragility_score ?? "Unavailable"}% · Level 3 ${level3.status || "Not Ready"} (${level3.readiness_percent ?? "Unavailable"}%) · ${escalationCounts.Critical || 0} critical / ${escalationCounts.Warning || 0} warning escalations · historical drift ${driftLab.historical_drift || memory.historical_trend || "Unavailable"} · persistence disabled`;
        governanceAssuranceSummary.classList.toggle("error", level3.status !== "Ready");
    }

    function renderOwnershipReport(reportData) {
        ownershipSummary.textContent = `${reportData.total_null_owner_rows} null-owner rows · ${reportData.resolvable_exact_guid_rows} exact GUID matches · ${reportData.manual_review_rows} require manual review · report is read-only`;
        renderSimpleTable(ownershipRows,
            ["Table","Record ID","Legacy owner","Matched user","Resolution"],
            reportData.rows.map(row=>[row.table,row.record_id,row.legacy_created_by,row.matched_email||"No exact AppUser match",row.recommended_action]),
            "No historical null-owner rows found.");
        ownershipScript.value = reportData.generated_update_script;
        ownershipRollbackScript.value = reportData.generated_rollback_script;
        ownershipSummary.textContent += ` · verified candidate set ${reportData.total_null_owner_rows}/${reportData.expected_exact_guid_candidate_count}: ${reportData.candidate_validation.replaceAll("_", " ")} · exact GUID matches ${reportData.resolvable_exact_guid_rows}`;
    }

    function renderPhase8Readiness(data) {
        phase8Recommendation.textContent = `${data.recommendation} Phase 7 migration: ${data.phase7_migration_applied ? "applied" : "not detected"}. Native RLS remains ${data.rls.enabled ? "enabled" : "disabled"}; this dashboard never enables it.`;
        phase8Recommendation.classList.toggle("error", data.recommendation.startsWith("NO-GO"));
        phase8Metrics.replaceChildren();
        const workforce = data.workforce || {};
        [
            [data.ownership.coverage_percent == null ? "Not available" : `${data.ownership.coverage_percent}%`, "Ownership coverage"],
            [data.runtime_ownership.coverage_percent == null ? "No records" : `${data.runtime_ownership.coverage_percent}%`, "Runtime ownership coverage"],
            [workforce.ready_candidates ?? "Migration required", "Ready candidates"],
            [workforce.strong_candidates ?? "Migration required", "Strong candidates"],
            [workforce.upskill_candidates ?? "Migration required", "Upskill candidates"],
            [workforce.workforce_requests ?? "Migration required", "Workforce requests"],
            [workforce.reused_agents ?? "Migration required", "Reused agents"],
            [workforce.workforce_reuse_percent == null ? "Not available" : `${workforce.workforce_reuse_percent}%`, "Workforce reuse"],
            [workforce.utilization_percent == null ? "Not available" : `${workforce.utilization_percent}%`, "Utilization"],
            [`${data.rls.policy_coverage_percent}%`, "Enabled RLS predicate coverage"],
        ].forEach(([value, label]) => {
            const metric = el("div", "phase8-metric");
            metric.append(el("strong", "", value), el("span", "", label));
            phase8Metrics.append(metric);
        });
        const runtimeRows = Object.entries(data.runtime_ownership.tables).map(([name, item]) => [
            name, `${item.valid_rows}/${item.total_rows}`, item.coverage_percent == null ? "No records" : `${item.coverage_percent}%`,
        ]);
        const policyRows = data.rls.tables.map(item => [item.table, item.covered ? "Covered" : "Not covered"]);
        const checkLabels = {
            phase7_migration_applied: "Phase 7 migration applied",
            historical_ownership_coverage_100_percent: "Historical ownership coverage complete",
            runtime_ownership_coverage_100_percent: "Runtime lineage coverage complete",
            all_rls_tables_have_enabled_predicates: "Enabled RLS predicates cover all required tables",
            runtime_tables_present: "Required runtime tables present",
            active_assignments_certified: "Active assignments use currently certified agents",
            active_assignments_with_capacity_and_workload: "Active assignments satisfy capacity and workload",
            active_assignments_audited: "Active assignments have traceable audit evidence",
        };
        phase8Details.replaceChildren(
            renderSimpleTableElement(["Go/No-Go gate", "Status"], Object.entries(data.checks).map(([key, passed]) => [checkLabels[key] || key, passed ? "Pass" : "Fail"]), "No readiness checks reported."),
            renderSimpleTableElement(["Runtime table", "Valid lineage / total", "Coverage"], runtimeRows, "No runtime tables reported."),
            renderSimpleTableElement(["RLS table", "Enabled predicate"], policyRows, "No RLS table coverage reported."),
            renderSimpleTableElement(["Assignment validation", "Verified / total"], [
                ["Active agent", `${data.assignment_validation.active_agent_assignments}/${data.assignment_validation.active_assignments}`],
                ["Latest certifications passed", `${data.assignment_validation.certified_agent_assignments}/${data.assignment_validation.active_assignments}`],
                ["Capacity and workload", `${data.assignment_validation.capacity_and_workload_assignments}/${data.assignment_validation.active_assignments}`],
                ["Audit trail coverage", data.assignment_validation.audit_coverage_percent == null ? "No active assignments" : `${data.assignment_validation.audit_coverage_percent}%`],
            ], "No assignments recorded; no assignment results are fabricated."),
            el("p", "empty", `Adapter enablement: ${data.execution_adapter_enablement.secret_vault_integration}; connectivity probe: ${data.execution_adapter_enablement.connectivity_probe}. ${data.execution_adapter_enablement.blocker} No health response is simulated.`),
        );
    }

    function renderPhase9Readiness(data) {
        phase9Recommendation.textContent = `${data.recommendation} · as of ${new Date(data.as_of_utc).toLocaleString()}. No control state was changed.`;
        phase9Recommendation.classList.toggle("error", data.recommendation === "NO-GO");
        phase9Metrics.replaceChildren();
        const labels = {
            governance_readiness: "Governance readiness",
            workforce_readiness: "Workforce readiness",
            runtime_readiness: "Runtime readiness",
            security_readiness: "Security readiness",
            operational_readiness: "Operational readiness",
            overall_platform_readiness: "Overall platform readiness",
        };
        Object.entries(data.metrics).forEach(([key, metric]) => {
            const item = el("div", "phase8-metric");
            item.append(el("strong", "", `${metric.percent}%`), el("span", "", `${labels[key] || key} · ${metric.passed}/${metric.total} verified gates`));
            phase9Metrics.append(item);
        });
        phase9Workforce.replaceChildren();
        const workforce = data.workforce || {};
        const readinessValues = [
            [workforce.ready_candidates, "Ready Candidates"],
            [workforce.strong_candidates, "Strong Candidates"],
            [workforce.upskill_candidates, "Upskill Candidates"],
            [workforce.workforce_requests, "New Workforce Requests"],
            [workforce.reused_agents, "Reused Agents"],
            [workforce.workforce_reuse_percent == null ? "Not available" : `${workforce.workforce_reuse_percent}%`, "Workforce Reuse"],
            [workforce.utilization_percent == null ? "Not available" : `${workforce.utilization_percent}%`, "Utilization"],
            [workforce.active_skill_coverage_percent == null ? "Not available" : `${workforce.active_skill_coverage_percent}%`, "Active Skill Coverage"],
            [workforce.active_certification_coverage_percent == null ? "Not available" : `${workforce.active_certification_coverage_percent}%`, "Active Certification Coverage"],
            ["Not Priced", "Workforce Savings"],
        ];
        readinessValues.forEach(([value, label]) => {
            const item = el("div", "phase9-workforce-item");
            item.append(el("strong", "", value ?? "Not available"), el("span", "", label));
            phase9Workforce.append(item);
        });
        phase9Blockers.replaceChildren();
        if (!data.blockers.length) phase9Blockers.append(el("p", "empty", "No measured blockers."));
        else {
            phase9Blockers.append(el("h4", "", "Readiness blockers"));
            const list = document.createElement("ul");
            data.blockers.forEach(blocker => list.append(el("li", "", blocker.replaceAll("_", " "))));
            phase9Blockers.append(list);
        }
        renderExecutiveReadinessView(document.getElementById("executiveReadinessView").value);
    }

    function renderPhase10Launch(data) {
        phase10Recommendation.textContent = `${data.recommendation} · as of ${new Date(data.as_of_utc).toLocaleString()}. No actions were performed.`;
        phase10Recommendation.classList.toggle("error", data.recommendation === "NO-GO");
        phase10Overall.textContent = `Overall Readiness: ${data.overall_readiness_percent}%`;
        phase10StatusCards.replaceChildren();
        const cards = [
            ["Ownership", `${data.ownership_status.exact_guid_matches}/${data.ownership_status.candidate_count} exact · ${data.ownership_status.unresolved_records} unresolved`],
            ["Adapter", `${data.adapter_status.configured_count} configured · ${data.adapter_status.healthy_count} real healthy`],
            ["Models", `${data.model_status.approved_count} approved · ${data.model_status.pending_reviews} pending`],
            ["Certification", `${data.certification_status.campaign_ready_agents}/${data.certification_status.campaign_agents} campaign agents ready`],
            ["Runtime", `${data.runtime_status.assignments_ready} assignments · ${data.runtime_status.queue_ready} queue · ${data.runtime_status.execution_ready} execution · ${data.runtime_status.deliverables_ready ?? "not available"} deliverables`],
            ["RLS", `${data.rls_status.status} · ${data.rls_status.enabled_predicate_coverage_percent}% predicate coverage`],
        ];
        cards.forEach(([title, value]) => {
            const card = el("article", "phase10-status-card");
            card.append(el("strong", "", title), el("span", "", value));
            phase10StatusCards.append(card);
        });
        const domainLabels = {
            governance_readiness: "Governance Readiness", workforce_readiness: "Workforce Readiness",
            runtime_readiness: "Runtime Readiness", security_readiness: "Security Readiness",
            model_readiness: "Model Readiness", adapter_readiness: "Adapter Readiness",
            ownership_readiness: "Ownership Readiness", rls_readiness: "RLS Readiness",
        };
        phase10Domains.replaceChildren();
        Object.entries(data.readiness_domains).forEach(([key, ready]) => {
            const item = el("div", `phase10-domain${ready ? " ready" : " blocked"}`);
            item.append(el("strong", "", domainLabels[key] || key), el("span", "", ready ? "Ready" : "Blocked"));
            phase10Domains.append(item);
        });
        phase10Blockers.replaceChildren();
        if (!data.blockers.length) phase10Blockers.append(el("p", "empty", "No measured launch blockers. This is not deployment authorization."));
        else {
            phase10Blockers.append(el("h4", "", "Launch blockers"));
            const list = document.createElement("ul");
            data.blockers.forEach(blocker => list.append(el("li", "", blocker)));
            phase10Blockers.append(list);
        }
    }

    function renderCertificationCampaign(data) {
        certificationCampaign.replaceChildren();
        data.campaigns.forEach(campaign => {
            const card = el("article", "campaign-card");
            card.append(
                el("h4", "", campaign.campaign_role),
                el("p", "campaign-meta", `${campaign.role_profile_status} · ${campaign.ready_count}/${campaign.agent_count} ready`),
            );
            if (campaign.role_profile_status !== "Active") {
                card.append(el("p", "campaign-blocker", campaign.blocking_evidence[0]));
            }
            campaign.agents.forEach(agent => {
                const row = el("div", "campaign-agent");
                row.append(el("strong", "", `${agent.agent_name} · ${agent.status} · ${agent.readiness}`));
                row.append(renderSimpleTableElement(["Skill", "Current", "Required", "Status", "Evidence"],
                    agent.skills.map(skill => [skill.name, skill.current_proficiency, skill.required_proficiency, skill.status, skill.evidence_recorded ? "Recorded" : "Missing"]),
                    "No required skill rows."));
                row.append(renderSimpleTableElement(["Certification", "Latest passed", "Evidence"],
                    Object.entries(agent.certifications).map(([name, value]) => [name, value.passed ? "Yes" : "No", value.evidence_recorded ? "Recorded" : "Missing"]),
                    "No certifications recorded."));
                if (agent.blocking_evidence.length) {
                    const blockers = document.createElement("ul");
                    blockers.className = "campaign-blocker-list";
                    agent.blocking_evidence.forEach(blocker => blockers.append(el("li", "", blocker)));
                    row.append(blockers);
                }
                card.append(row);
            });
            certificationCampaign.append(card);
        });
    }

    function renderAdapterDeploymentWizard(data) {
        adapterDeploymentWizard.replaceChildren();
        adapterDeploymentWizard.append(el("p", "empty", `Provider calls performed: ${data.provider_calls_performed ? "yes" : "no"}. Runtime enabled: ${data.runtime_enabled ? "yes" : "no"}.`));
        data.providers.forEach(provider => {
            const row = el("article", "adapter-row");
            const info = el("div");
            info.append(el("strong", "", provider.provider_name), el("small", "", `${provider.configuration_status} · credential reference ${provider.secret_reference_format_valid ? "valid format" : "not configured/invalid"} · health ${provider.health_status}`));
            row.append(info);
            const verify = el("button", "action", "Verify credential reference");
            verify.type = "button";
            verify.disabled = !provider.secret_reference_format_valid;
            verify.title = "Resolves the secret reference only; this does not call the model provider.";
            verify.addEventListener("click", async () => {
                verify.disabled = true;
                try {
                    const result = await request(`/operations/execution-adapters/${provider.provider_code}/verify-credential`, { method: "POST" });
                    setStatus(`${provider.provider_name}: ${result.status}. ${result.details} Provider call: no.`);
                    await loadOperationsDashboard();
                } catch (error) { setStatus(error.message, true); verify.disabled = false; }
            });
            row.append(verify, el("span", "campaign-meta", provider.blockers.join(" · ") || "Configuration validation passed; not enabled."));
            adapterDeploymentWizard.append(row);
        });
    }

    function renderMigration24Validation(data) {
        migration24Validation.replaceChildren();
        migration24Validation.append(el("div", `phase11-validation ${data.deployment_recommendation.startsWith("NO-GO") ? "blocked" : "ready"}`,
            `${data.static_validation} · ${data.deployment_recommendation} Database dry run: not executed. Migration applied: ${data.migration_already_applied ? "yes" : "no"}.`));
        migration24Validation.append(renderSimpleTableElement(["Dependency", "Status"],
            data.dependencies.map(item => [item.table, item.present ? "Present" : "Missing"]), "No migration dependencies reported."));
        migration24Validation.append(renderSimpleTableElement(["Static check", "Result"], [
            ["Migration file present", data.script_present ? "Yes" : "No"],
            ["Required schema contracts", data.required_contracts_present ? "Present" : `Missing: ${data.missing_contracts.join(", ")}`],
            ["Guarded table creation", data.create_is_guarded ? "Yes" : "No"],
            ["Guarded constraint replacement", data.constraint_replacement_is_guarded ? "Yes" : "No"],
            ["Destructive table/column operations", data.destructive_table_or_column_operations.length ? data.destructive_table_or_column_operations.join("; ") : "None found"],
            ["Rollback validation", data.rollback_validation],
        ], "No static validation results."));
    }

    function renderModelOnboardingSummary(data) {
        modelOnboardingSummary.replaceChildren();
        modelOnboardingSummary.append(el("p", "empty", `Providers recorded: ${data.providers.length} · model entries: ${data.models.length} · automatic approval: ${data.approval_automatic ? "enabled" : "disabled"}. Proposal uses the existing governed model wizard; no proposal or approval was created by this package.`));
        modelOnboardingSummary.append(renderSimpleTableElement(["Provider", "Status"], data.providers.map(row => [row.ProviderName, row.Status]), "No providers recorded."));
        modelOnboardingSummary.append(renderSimpleTableElement(["Supported provider", "Registry status"],
            data.supported_provider_onboarding.map(row => [row.provider_name,row.registry_status]), "No provider onboarding data."));
        modelOnboardingSummary.append(renderSimpleTableElement(["Provider", "Model", "Version", "Status", "Created", "Approved"],
            data.models.map(row => [row.ProviderName,row.ModelName,row.ModelVersion,row.Status,row.CreatedAtUtc,row.ApprovedAtUtc]),
            "No model proposals recorded."));
        modelOnboardingSummary.append(renderSimpleTableElement(["Provider", "Model", "Version", "Latest decision", "Reason", "Evidence"],
            data.models.filter(row => row.LatestDecision).map(row => [row.ProviderName,row.ModelName,row.ModelVersion,row.LatestDecision,row.LatestDecisionReason,row.LatestDecisionEvidence]),
            "No model review decisions recorded."));
        modelOnboardingSummary.append(renderSimpleTableElement(["Proposal audit", "Provider", "Model", "Version", "Reason", "Evidence reference", "Created"],
            data.proposal_evidence.map(row => [row.audit_id,row.provider,row.model,row.version,row.reason,row.evidence_reference,row.created_at_utc]),
            "No model proposal evidence recorded."));
        modelOnboardingSummary.append(renderSimpleTableElement(["Pending review", "Provider", "Model", "Version", "Created"],
            data.pending_review_blockers.map(row => [row.blocker,row.provider,row.model,row.version,row.created_at_utc]), "No pending model review blockers."));
        modelOnboardingSummary.append(renderSimpleTableElement(["Provider onboarding checklist"],
            data.provider_onboarding_checklist.map(item => [item]), "No provider onboarding steps."));
        modelOnboardingSummary.append(renderSimpleTableElement(["Review checklist"], data.review_checklist.map(item => [item]), "No model review checklist."));
    }

    async function renderExecutiveReadinessView(view) {
        executiveReadinessMetrics.replaceChildren();
        try {
            const data = await request(`/operations/executive-readiness/${encodeURIComponent(view)}`);
            Object.entries(data.scorecards).forEach(([key, metric]) => {
                const label = key.replaceAll("_", " ");
                const item = el("div", "phase9-executive-metric", `${label}: ${metric.percent}% · ${metric.passed}/${metric.total}`);
                executiveReadinessMetrics.append(item);
            });
        } catch (error) { executiveReadinessMetrics.append(el("p", "empty", error.message)); }
    }

    async function renderExecutionAdapters(items, auditRows) {
        adapterConfigs.replaceChildren();
        const catalogs = await request("/governance/models/approved");
        for (const item of items) {
            const row=el("article","adapter-row");
            const summary=el("div");
            const status=item.health_status||"NotChecked";
            summary.append(el("strong","",item.provider_name),el("small","",`${item.config?.Status||"Not configured"} · latest recorded check ${status} · ${item.health_detail||"No check recorded"}`));
            const check=el("button","action",item.config?"Run authenticated probe":"Configure before probe");check.type="button";
            check.disabled=!item.config;
            check.title="Runs a real provider API request using the configured secret resolver; no response body or secret is retained.";
            check.addEventListener("click",()=>runAdapterConfigurationCheck(item.provider_code,check));
            row.append(summary,check);
            const form=document.createElement("form");form.className="adapter-form";
            const endpoint=document.createElement("input");endpoint.type="url";endpoint.required=true;endpoint.placeholder="HTTPS provider endpoint";endpoint.setAttribute("aria-label",`${item.provider_name} endpoint`);
            if(item.config?.EndpointUrl)endpoint.value=item.config.EndpointUrl;
            const deployment=document.createElement("input");deployment.required=true;deployment.maxLength=200;deployment.placeholder="Deployment or model alias";deployment.setAttribute("aria-label",`${item.provider_name} deployment`);
            if(item.config?.DeploymentName)deployment.value=item.config.DeploymentName;
            const modelSelect=document.createElement("select");modelSelect.required=true;modelSelect.setAttribute("aria-label",`${item.provider_name} approved model`);
            modelSelect.append(new Option("Select approved catalog model",""));
            catalogs.filter(model=>model.ProviderCode===item.provider_code).forEach(model=>{const option=new Option(`${model.ModelName} · ${model.ModelVersion}`,model.ModelCatalogID);option.selected=String(item.config?.ModelCatalogID||"")===String(model.ModelCatalogID);modelSelect.append(option);});
            const secret=document.createElement("input");secret.required=true;secret.maxLength=500;secret.placeholder=item.config?.SecretReferenceConfigured?"Secret reference configured (enter replacement to change)":"External secret-manager reference";secret.setAttribute("aria-label",`${item.provider_name} secret reference`);secret.autocomplete="off";
            const save=el("button","action primary",item.config?"Update configuration":"Save configuration · runtime disabled");save.type="submit";
            form.append(endpoint,deployment,modelSelect,secret,save);
            form.addEventListener("submit",async event=>{event.preventDefault();await saveAdapterConfiguration(item.provider_code,{endpoint_url:endpoint.value,deployment_name:deployment.value,model_catalog_id:modelSelect.value,secret_reference:secret.value},save);});
            row.append(form);adapterConfigs.append(row);
        }
        renderSimpleTable(adapterAudit,["When","Actor","Action","Outcome","Details"],
            auditRows.map(row=>[new Date(row.CreatedAtUtc).toLocaleString(),row.ActorID,row.Action,row.Outcome,row.Details]),
            "No adapter changes or health checks have been recorded.");
    }

    async function saveAdapterConfiguration(provider, payload, button) {
        if(!payload.model_catalog_id)return setStatus("Select an approved catalog model for this provider.",true);
        const reason=window.prompt("Reason for this adapter configuration update:");if(!reason||reason.trim().length<10)return;
        button.disabled=true;
        try{await request(`/operations/execution-adapters/${provider}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});setStatus("Adapter configuration saved. Provider connectivity was not tested and runtime remains disabled.");await loadOperationsDashboard();}
        catch(error){setStatus(error.message,true);button.disabled=false;}
    }

    async function runAdapterConfigurationCheck(provider,button){
        button.disabled=true;
        try{const result=await request(`/operations/execution-adapters/${provider}/health-check`,{method:"POST"});setStatus(result.details);await loadOperationsDashboard();}
        catch(error){setStatus(error.message,true);button.disabled=false;}
    }

    function renderModelLifecycle(data){
        modelLifecycle.replaceChildren();
        data.lifecycle.forEach(row=>modelLifecycle.append(el("div","ops-metric",`${row.Status}: ${row.ModelCount}`)));
        if(!data.lifecycle.length)modelLifecycle.append(el("p","empty","No models are registered."));
        const pending=el("div");pending.append(el("h4","","Pending approval aging"));
        pending.append(renderSimpleTableElement(["Provider","Model","Version","Pending hours"],data.pending_approval_aging.map(x=>[x.ProviderName,x.ModelName,x.ModelVersion,x.PendingHours]),"No pending model proposals."));
        pending.append(el("p","empty",`Pending reviews: ${data.pending_reviews}. Approval SLA: ${data.approval_sla?.configured ? `${data.approval_sla.target_hours} hours` : "Not Configured"}.`));
        modelLifecycle.append(pending);
        modelLifecycle.append(el("h4","","Model usage"));
        modelLifecycle.append(renderSimpleTableElement(["Provider","Model","Version","Status","Active agents","Active assignments","Executions"],
            (data.model_usage || []).map(x=>[x.ProviderName,x.ModelName,x.ModelVersion,x.Status,x.ActiveAgentCount,x.ActiveAssignmentCount,x.ExecutionCount]),"No model usage or catalog rows."));
        const approved=el("div");approved.append(el("h4","","Approved models"));
        data.approved_models.forEach(item=>{
            const row=el("div","adapter-row");
            row.append(el("strong","",`${item.ProviderName} · ${item.ModelName} · ${item.ModelVersion} · retirement impact: ${item.AgentImpactCount ?? "not available"} agents, ${item.ActiveAssignmentImpactCount ?? "not available"} active assignments, ${item.RunningExecutionImpactCount ?? "not available"} running executions`));
            const retire=el("button","action danger","Retire");retire.type="button";
            retire.addEventListener("click",()=>retireModel(item,retire));row.append(retire);approved.append(row);
        });
        if(!data.approved_models.length)approved.append(el("p","empty","No approved models to retire."));
        modelLifecycle.append(approved);
    }

    async function retireModel(item,button){
        const reason=window.prompt(`Retirement reason for ${item.ModelName} ${item.ModelVersion}:`);if(!reason||reason.trim().length<10)return;
        const evidence=window.prompt("Attach migration, deprecation, or risk evidence reference (20+ characters):");if(!evidence||evidence.trim().length<20)return;
        button.disabled=true;
        try{await request(`/operations/models/${item.ModelCatalogID}/retire`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason:reason.trim(),evidence:evidence.trim()})});setStatus(`${item.ModelName} retired; confirm agent migration completed.`);await loadOperationsDashboard();}
        catch(error){setStatus(error.message,true);button.disabled=false;}
    }

    function renderSimpleTableElement(headers,rows,emptyMessage){
        if(!rows.length)return el("p","empty",emptyMessage);
        const table=document.createElement("table"),head=table.createTHead().insertRow(),body=table.createTBody();
        headers.forEach(name=>{const cell=el("th","",name);cell.scope="col";head.append(cell);});
        rows.forEach(values=>{const row=body.insertRow();values.forEach(value=>row.insertCell().textContent=String(value??"Not recorded"));});
        const wrap=el("div","table-wrap");wrap.append(table);return wrap;
    }

    function renderCertificationDashboard(data){
        certificationDashboard.replaceChildren();
        certificationDashboard.append(el("div","ops-metric",`Fully certified agents: ${data.fully_certified_agent_count}/${data.agent_count} (${data.certification_completion_percent}%)`));
        certificationDashboard.append(el("div","ops-metric",`Active agent certification coverage: ${data.active_agent_certification_coverage.certified_agents}/${data.active_agent_certification_coverage.active_agents} (${data.active_agent_certification_coverage.coverage_percent ?? "Not available"}%)`));
        certificationDashboard.append(el("div","ops-metric",`Active skill coverage: ${data.active_agent_skill_coverage.agents_meeting_required_active_skills}/${data.active_agent_skill_coverage.active_agents_with_role_requirements} (${data.active_agent_skill_coverage.coverage_percent ?? "Not available"}%)`));
        certificationDashboard.append(renderSimpleTableElement(["Skill status","Assignments"],data.skill_validation_status.map(x=>[x.Status,x.SkillAssignmentCount]),"No skill assignments."));
        certificationDashboard.append(renderSimpleTableElement(["Evaluation","Latest reviews","Passed","Pass rate","Avg score"],data.evaluation_pass_rates.map(x=>[x.EvaluationType,x.LatestEvaluationCount,x.LatestPassedCount,`${x.pass_rate_percent}%`,x.LatestAverageScore==null?"Not recorded":Number(x.LatestAverageScore).toFixed(1)]),"No evaluations recorded."));
        certificationDashboard.append(renderSimpleTableElement(["Year","Month","Evaluation","Count","Passed"],data.evaluation_trend.map(row=>[row.EvaluationYear,row.EvaluationMonth,row.EvaluationType,row.EvaluationCount,row.PassedCount]),"No evaluation trend records."));
        certificationDashboard.append(el("p","empty",`${data.expiry.label}: ${data.expiry.message}`));
    }

    function renderOperationalScorecard(data){
        operationalScorecard.replaceChildren();
        operationalScorecard.append(el("div","ops-metric",`Readiness: ${data.readiness_percent}% · ${data.status}`));
        operationalScorecard.append(el("p","empty",`Company ${data.company_id} · as of ${new Date(data.as_of_utc).toLocaleString()} · Native RLS ${data.rls_enabled?"enabled":"disabled"}`));
        const labels={users_ready:"Users Ready",agents_ready:"Agents Ready",models_approved:"Models Approved",assignments_created:"Assignments Created",executions_running:"Executions Running",deliverables_generated:"Deliverables Generated"};
        Object.entries(data.scorecard).forEach(([key,value])=>{
            const display=typeof value==="object"?`${value.ready}/${value.total}`:value;
            operationalScorecard.append(el("div","ops-metric",`${labels[key]||key}: ${display}`));
        });
        operationalScorecard.append(el("p","empty",`Execution adapter configured: ${data.execution_adapter_configured?"yes":"no"}.`));
    }

    function renderModelCatalog() {
        const container = document.getElementById("modelCatalog");
        container.replaceChildren();
        if (!modelCatalog.length) {
            container.append(el("p", "empty", "No model proposals exist. Only separately approved catalog entries can be assigned to agents."));
            return;
        }
        const table = document.createElement("table");
        const header = table.createTHead().insertRow();
        ["Provider", "Model", "Version", "Status", "Reviewer action"].forEach((name) => {
            const cell = el("th", "", name); cell.scope = "col"; header.append(cell);
        });
        const body = table.createTBody();
        modelCatalog.forEach((item) => {
            const row = body.insertRow();
            [item.ProviderName, item.ModelName, item.ModelVersion, item.Status].forEach(value => row.insertCell().textContent = String(value));
            const actionCell = row.insertCell();
            if (item.Status === "Pending") {
                const approve = el("button", "action primary", "Approve");
                const reject = el("button", "action danger", "Reject");
                approve.type = reject.type = "button";
                approve.addEventListener("click", () => decideModel(item, "Approved", approve));
                reject.addEventListener("click", () => decideModel(item, "Rejected", reject));
                const controls = el("div", "registry-decision");
                controls.append(approve, reject);
                actionCell.append(controls);
            } else {
                actionCell.textContent = item.LatestDecision || "Decision recorded";
            }
        });
        container.append(table);
    }

    async function submitModelProposal(event) {
        event.preventDefault();
        const form = event.currentTarget;
        const submit = form.querySelector("button[type='submit']");
        submit.disabled = true;
        const payload = {
            provider: document.getElementById("proposalProvider").value,
            model: document.getElementById("proposalModel").value.trim(),
            version: document.getElementById("proposalVersion").value.trim(),
            reason: document.getElementById("proposalReason").value.trim(),
            evidence: document.getElementById("proposalEvidence").value.trim(),
        };
        try {
            const result = await request("/governance/models/proposals", {
                method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
            });
            setStatus(`Proposal created as ${result.status}; it is not selectable for agents until approved.`);
            form.reset();
            await loadGovernanceData();
        } catch (error) { setStatus(error.message, true); }
        finally { submit.disabled = false; }
    }

    async function decideModel(item, decision, button) {
        const reason = window.prompt(`Reason to ${decision.toLowerCase()} ${item.ProviderName} ${item.ModelName} ${item.ModelVersion}:`);
        if (!reason || reason.trim().length < 10) return;
        const evidence = window.prompt("Attach the approved procurement/security reference (minimum 20 characters):");
        if (!evidence || evidence.trim().length < 20) return;
        button.disabled = true;
        try {
            await request(`/governance/models/${item.ModelCatalogID}/decision`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ decision, reason: reason.trim(), evidence: evidence.trim() }),
            });
            setStatus(`${item.ModelName} ${decision.toLowerCase()} with review evidence recorded.`);
            await Promise.all([loadGovernanceData(), loadReadiness()]);
        } catch (error) { setStatus(error.message, true); button.disabled = false; }
    }

    async function loadGovernanceData() {
        [modelCatalog, approvedModels, evaluationTemplates] = await Promise.all([
            request("/governance/models/catalog"),
            request("/governance/models/approved"),
            request("/governance/evaluation-templates"),
        ]);
        renderModelCatalog();
    }

    function renderModelCatalog() {
        const container = document.getElementById("modelCatalog");
        container.replaceChildren();
        if (!modelCatalog.length) {
            container.append(el("p", "empty", "No model proposals yet. Proposed models remain unavailable to agents until approved."));
            return;
        }
        const table = document.createElement("table");
        const header = table.createTHead().insertRow();
        ["Provider", "Model", "Version", "Status", "Decision"].forEach((name) => {
            const cell = el("th", "", name); cell.scope = "col"; header.append(cell);
        });
        const body = table.createTBody();
        modelCatalog.forEach((item) => {
            const row = body.insertRow();
            [item.ProviderName, item.ModelName, item.ModelVersion, item.Status].forEach((value) => row.insertCell().textContent = String(value));
            const decision = row.insertCell();
            if (item.Status === "Pending") {
                const approve = el("button", "action primary", "Approve");
                const reject = el("button", "action danger", "Reject");
                approve.type = reject.type = "button";
                approve.addEventListener("click", () => reviewModel(item, "Approved", approve));
                reject.addEventListener("click", () => reviewModel(item, "Rejected", reject));
                const actions = el("div", "registry-decision");
                actions.append(approve, reject);
                decision.append(actions);
            } else {
                decision.textContent = item.LatestDecision || "No decision history";
            }
        });
        container.append(table);
    }

    async function proposeModel(event) {
        event.preventDefault();
        const button = event.currentTarget.querySelector("button[type='submit']");
        button.disabled = true;
        const payload = {
            provider: document.getElementById("proposalProvider").value,
            model: document.getElementById("proposalModel").value.trim(),
            version: document.getElementById("proposalVersion").value.trim(),
            reason: document.getElementById("proposalReason").value.trim(),
            evidence: document.getElementById("proposalEvidence").value.trim(),
        };
        try {
            const result = await request("/governance/models/proposals", {
                method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
            });
            setStatus(`Model proposal recorded as ${result.status}. It cannot be assigned until separately approved.`);
            event.currentTarget.reset();
            await loadGovernanceData();
        } catch (error) { setStatus(error.message, true); }
        finally { button.disabled = false; }
    }

    async function reviewModel(item, decision, button) {
        const reason = window.prompt(`Reason to ${decision.toLowerCase()} ${item.ProviderName} ${item.ModelName} ${item.ModelVersion}:`);
        if (!reason || reason.trim().length < 10) return;
        const evidence = window.prompt("Approval/rejection evidence reference (minimum 20 characters):");
        if (!evidence || evidence.trim().length < 20) return;
        button.disabled = true;
        try {
            await request(`/governance/models/${item.ModelCatalogID}/decision`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ decision, reason: reason.trim(), evidence: evidence.trim() }),
            });
            setStatus(`${item.ModelName} ${decision.toLowerCase()} decision recorded with evidence.`);
            await Promise.all([loadGovernanceData(), loadReadiness()]);
        } catch (error) { setStatus(error.message, true); button.disabled = false; }
    }

    function renderMappings() {
        mappingTable.replaceChildren();
        const table = document.createElement("table");
        const header = table.createTHead().insertRow();
        ["User", "Company", "Department", "Position", "Validation"].forEach((name) => {
            const cell = el("th", "", name);
            cell.scope = "col";
            header.append(cell);
        });
        const body = table.createTBody();
        mappingData.users.filter((user) => user.IsActive).forEach((user) => {
            const row = body.insertRow();
            const userCell = row.insertCell();
            userCell.className = "user-cell";
            userCell.append(el("strong", "", user.DisplayName), el("small", "", user.Email));
            const companyCell = row.insertCell();
            const company = makeSelect(`${user.DisplayName} company`, mappingData.companies, "CompanyID", "CompanyName", user.CompanyID);
            companyCell.append(company);
            const departmentCell = row.insertCell();
            const department = makeSelect(`${user.DisplayName} department`, mappingData.departments, "DepartmentID", "DepartmentName", user.DepartmentID,
                (item) => !company.value || String(item.CompanyID) === company.value);
            departmentCell.append(department);
            const positionCell = row.insertCell();
            const position = makeSelect(`${user.DisplayName} position`, mappingData.positions, "PositionID", "PositionName", user.PositionID,
                (item) => !department.value || String(item.DepartmentID) === department.value);
            positionCell.append(position);
            const validateCell = row.insertCell();
            const save = el("button", "save-map", user.CompanyID && user.DepartmentID && user.PositionID ? "Save mapping" : "Map user");
            save.type = "button";
            company.addEventListener("change", () => {
                department.replaceChildren(...makeSelect("Department", mappingData.departments, "DepartmentID", "DepartmentName", "", (item) => String(item.CompanyID) === company.value).children);
                position.replaceChildren(new Option("Select position", ""));
            });
            department.addEventListener("change", () => {
                const refreshed = makeSelect("Position", mappingData.positions, "PositionID", "PositionName", "", (item) => String(item.DepartmentID) === department.value);
                position.replaceChildren(...refreshed.children);
            });
            save.addEventListener("click", async () => {
                if (!company.value || !department.value || !position.value) return setStatus("Choose an active company, department, and position.", true);
                save.disabled = true;
                const mapping = { company_id: company.value, department_id: department.value, position_id: position.value };
                try {
                    await request(`/admin/org-mappings/${user.UserID}/validate`, {
                        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(mapping),
                    });
                    const result = await request(`/admin/org-mappings/${user.UserID}`, {
                        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(mapping),
                    });
                    setStatus(result.ready ? "Mapping saved. Organization checks now pass; workspace services are ready." : "Mapping saved. Other active users still need valid organization mappings.");
                    await Promise.all([loadMappingState(), loadMappingReport()]);
                } catch (error) { setStatus(error.message, true); save.disabled = false; }
            });
            validateCell.append(save);
            if (user.LegacyDepartment && !user.DepartmentID) {
                validateCell.append(el("small", "gaps", `Legacy label: ${user.LegacyDepartment} (not auto-mapped)`));
            }
        });
        mappingTable.append(table);
        loadMappingReport().catch((error) => setStatus(error.message, true));
    }

    function renderReadiness() {
        skillSummary.replaceChildren();
        const activeAgents = readinessData.agents.filter((agent) => agent.status === "Active").length;
        const summaryValues = [
            [readinessData.agents.length, "Agents in company"],
            [activeAgents, "Active agents"],
            [readinessData.skill_gaps.length, "Required skills with no available agent"],
        ];
        summaryValues.forEach(([value, name]) => {
            const item = el("div", "summary-item");
            item.append(el("strong", "", value), el("span", "", name));
            skillSummary.append(item);
        });
        agentList.replaceChildren();
        readinessData.agents.forEach((agent) => {
            const card = el("article", "agent-card");
            const title = el("div", "agent-title");
            title.append(el("h3", "", agent.name), el("span", "status-pill", agent.status));
            card.append(title, el("p", "agent-meta", `${agent.agent_type} · ${agent.role_code || "No role code"} · role profile ${agent.role_profile_status || "Missing"} · workload ${agent.current_workload_percent}% · ${agent.active_assignments}/${agent.concurrent_task_limit} active assignments · ~${agent.available_hours_estimate}h estimated available/week`));
            const tags = el("div", "skill-tags");
            agent.skills.forEach((skill) => tags.append(el("span", "skill-tag", `${skill.name} ${skill.proficiency}/5 · ${skill.status}`)));
            if (!agent.skills.length) tags.append(el("span", "gaps", "No skill records"));
            card.append(tags);
            const requiredSkills = agent.required_skills.map((skill) => `${skill.name} ≥${skill.minimum_proficiency}/5`).join(" · ");
            card.append(el("p", "agent-meta", `Required skills: ${requiredSkills || "No active role profile requirements"}`));
            card.append(el("p", "gaps", agent.skill_gaps.length ? `Skill gaps: ${agent.skill_gaps.map((gap) => `${gap.skill} ${gap.active_proficiency}/${gap.required_proficiency}`).join(" · ")}` : "Required role skills are active."));
            card.append(el("p", "gaps", agent.certification_gaps.length ? `Certification gaps: ${agent.certification_gaps.join(", ")}` : "Required certifications passed."));
            const controls = el("div", "controls");
            if (agent.status === "Provisioning") {
                const model = document.createElement("select");
                model.setAttribute("aria-label", `Approved model for ${agent.name}`);
                model.append(new Option(approvedModels.length ? "Select approved model" : "No approved models", ""));
                approvedModels.forEach((item) => model.append(new Option(
                    `${item.ProviderName} · ${item.ModelName} · ${item.ModelVersion}`,
                    item.ModelCatalogID,
                )));
                const saveModel = el("button", "action primary", "Save model configuration");
                saveModel.type = "button";
                saveModel.disabled = !approvedModels.length;
                saveModel.addEventListener("click", () => configureModel(agent, model.value, saveModel));
                controls.append(model, saveModel);
                const evaluationTemplate = document.createElement("select");
                evaluationTemplate.setAttribute("aria-label", `Evaluation template for ${agent.name}`);
                evaluationTemplate.append(new Option("Select evaluation template", ""));
                evaluationTemplates.forEach((template) => evaluationTemplate.append(new Option(template.name, template.template_code)));
                const criteriaPanel = el("div", "evaluation-criteria");
                evaluationTemplate.addEventListener("change", () => renderEvaluationCriteria(evaluationTemplate.value, criteriaPanel));
                const recordEvaluation = el("button", "action", "Record evidence-backed evaluation");
                recordEvaluation.type = "button";
                recordEvaluation.addEventListener("click", () => recordCertification(agent, evaluationTemplate.value, criteriaPanel, recordEvaluation));
                controls.append(evaluationTemplate, criteriaPanel, recordEvaluation);
            }
            const skill = makeSelect("Approved skill", readinessData.skills_catalog, "SkillID", "Name", "");
            const proficiency = document.createElement("select");
            proficiency.setAttribute("aria-label", "Skill proficiency");
            [1, 2, 3, 4, 5].forEach((value) => proficiency.append(new Option(`${value}/5`, String(value))));
            const assign = el("button", "action", "Assign skill (pending)");
            assign.type = "button";
            assign.addEventListener("click", () => updateSkill(agent, skill.value, Number(proficiency.value), "assign", assign));
            controls.append(skill, proficiency, assign);
            const pendingSkills = agent.skills.filter((value) => value.status === "Pending");
            pendingSkills.forEach((pending) => {
                const approve = el("button", "action primary", `Approve ${pending.name}`);
                approve.type = "button";
                approve.addEventListener("click", () => updateSkill(agent, pending.skill_id, pending.proficiency, "approve", approve));
                controls.append(approve);
            });
            if (agent.status === "Provisioning") {
                const activate = el("button", "action primary", "Approve & activate (gated)");
                activate.type = "button";
                activate.addEventListener("click", () => activateAgent(agent, activate));
                controls.append(activate);
            }
            if (agent.status === "Active") {
                const deactivate = el("button", "action danger", "Deactivate");
                deactivate.type = "button";
                deactivate.addEventListener("click", () => deactivateAgent(agent, deactivate));
                controls.append(deactivate);
            }
            card.append(controls);
            agentList.append(card);
        });
    }

    function renderEvaluationCriteria(templateCode, container) {
        container.replaceChildren();
        const template = evaluationTemplates.find((item) => item.template_code === templateCode);
        if (!template) return;
        template.criteria.forEach((criterion) => {
            const row = el("label", "criterion-row");
            row.append(el("span", "", `${criterion.name}: ${criterion.description}`));
            const score = document.createElement("input");
            score.type = "number";
            score.min = "0";
            score.max = "100";
            score.value = "0";
            score.setAttribute("aria-label", `${criterion.name} score`);
            const evidence = document.createElement("textarea");
            evidence.minLength = 20;
            evidence.placeholder = "Criterion-specific evidence reference (20+ characters)";
            evidence.setAttribute("aria-label", `${criterion.name} evidence`);
            row.append(score, evidence);
            row.dataset.criterionCode = criterion.code;
            container.append(row);
        });
    }

    async function configureModel(agent, modelCatalogId, button) {
        if (!modelCatalogId) return setStatus("Select an approved model catalog entry.", true);
        const reason = window.prompt("Reason for assigning this approved model to the agent:");
        if (!reason || reason.trim().length < 5) return;
        button.disabled = true;
        try {
            await request(`/workforce/agents/${agent.agent_id}/model`, {
                method: "PUT", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ model_catalog_id: modelCatalogId, reason: reason.trim() }),
            });
            setStatus(`Model configuration saved for ${agent.name}; activation still requires validated skills and all certification gates.`);
            await loadReadiness();
        } catch (error) { setStatus(error.message, true); button.disabled = false; }
    }

    async function recordCertification(agent, templateCode, criteriaPanel, button) {
        if (!templateCode) return setStatus("Select an evaluation template.", true);
        const criteria = [...criteriaPanel.querySelectorAll(".criterion-row")].map((row) => ({
            criterion_code: row.dataset.criterionCode,
            score: Number(row.querySelector("input").value),
            evidence: row.querySelector("textarea").value.trim(),
        }));
        if (!criteria.length || criteria.some(item => !Number.isFinite(item.score) || item.score < 0 || item.score > 100 || item.evidence.length < 20)) {
            return setStatus("Enter a 0–100 score and at least 20 characters of evidence for every criterion.", true);
        }
        const reason = window.prompt("Reviewer rationale for this evaluation:");
        if (!reason || reason.trim().length < 5) return;
        button.disabled = true;
        try {
            await request(`/workforce/agents/${agent.agent_id}/evaluations`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ template_code: templateCode, criteria, reason: reason.trim() }),
            });
            setStatus(`${templateCode} evaluation recorded for ${agent.name}; activation still requires all gates to pass.`);
            await loadReadiness();
        } catch (error) { setStatus(error.message, true); button.disabled = false; }
    }

    async function updateSkill(agent, skillId, proficiency, action, button) {
        if (!skillId) return setStatus("Select an approved skill first.", true);
        const evidence = window.prompt(`Validation evidence for ${action} (minimum 20 characters):`);
        if (!evidence || evidence.trim().length < 20) return;
        const reason = window.prompt(`Reason for ${action}ing this skill assignment (minimum 5 characters):`);
        if (!reason || reason.trim().length < 5) return;
        button.disabled = true;
        try {
            await request(`/workforce/agents/${agent.agent_id}/skills`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ skill_id: skillId, proficiency, action, evidence: evidence.trim(), reason: reason.trim() }),
            });
            setStatus(`Skill ${action} completed for ${agent.name}.`);
            await loadReadiness();
        } catch (error) { setStatus(error.message, true); button.disabled = false; }
    }

    async function activateAgent(agent, button) {
        const reason = window.prompt("Approval reason for activating this agent after provider/model and evaluations have passed:");
        if (!reason || reason.trim().length < 5) return;
        button.disabled = true;
        try {
            const path = agent.provisioning_request_id
                ? `/workforce/requests/${agent.provisioning_request_id}/activate`
                : `/workforce/agents/${agent.agent_id}/activate`;
            const result = await request(path, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reason: reason.trim() }),
            });
            setStatus(result.message || "Agent activation approved.");
            await loadReadiness();
        } catch (error) { setStatus(error.message, true); button.disabled = false; }
    }

    async function deactivateAgent(agent, button) {
        const reason = window.prompt("Reason for deactivating this agent:");
        if (!reason || reason.trim().length < 5) return;
        button.disabled = true;
        try {
            await request(`/workforce/agents/${agent.agent_id}/deactivate`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reason: reason.trim() }),
            });
            setStatus(`${agent.name} deactivated; runtime credentials revoked.`);
            await loadReadiness();
        } catch (error) { setStatus(error.message, true); button.disabled = false; }
    }

    function renderCapacity() {
        capacityTable.replaceChildren();
        if (!capacityData.agents.length) return capacityTable.append(el("p", "empty", "No agents found in this company scope."));
        const table = document.createElement("table");
        const header = table.createTHead().insertRow();
        ["Agent", "Status", "Utilization", "Assignments", "Slots available", "Available hours/week", "Open task hours", "In-progress hours"].forEach((label) => {
            const cell = el("th", "", label); cell.scope = "col"; header.append(cell);
        });
        const body = table.createTBody();
        capacityData.agents.forEach((agent) => {
            const row = body.insertRow();
            [agent.agent_name, agent.status, `${agent.utilization_percent}%`, agent.active_assignments,
                agent.available_task_slots, `~${agent.estimated_available_hours}`, agent.open_estimated_task_hours,
                agent.in_progress_estimated_task_hours].forEach((value) => row.insertCell().textContent = String(value));
        });
        capacityTable.append(table);
    }

    async function loadReadiness() { readinessData = await request("/workforce/agent-readiness"); renderReadiness(); }
    async function loadCapacity() { capacityData = await request("/workforce/capacity"); renderCapacity(); }

    async function loadAll() {
        setStatus("Loading current mappings, agent readiness, and capacity…");
        try {
            await Promise.all([loadMappingState(), loadMappingReport()]);
        } catch (error) { setStatus(error.message, true); }
        try {
            await loadGovernanceData();
        } catch (error) {
            setStatus(`Model registry/templates are unavailable until migration 20 is applied: ${error.message}`);
        }
        try {
            await Promise.all([loadReadiness(), loadCapacity()]);
            if (approvedModels.length || evaluationTemplates.length) {
                setStatus("Live organization and workforce data loaded. No executions are simulated.");
            }
        } catch (error) {
            setStatus(`Organization mapping repair is available. Agent readiness and capacity remain gated: ${error.message}`);
        }
        try { await loadOperationsDashboard(); }
        catch (error) { setStatus(`Operational reports are unavailable: ${error.message}`, true); }
    }

    tabs.forEach((tab) => tab.addEventListener("click", () => {
        const selected = tab.dataset.tab;
        tabs.forEach((item) => {
            const active = item === tab;
            item.classList.toggle("active", active);
            item.setAttribute("aria-pressed", String(active));
        });
        Object.entries(panels).forEach(([name, panel]) => { panel.hidden = name !== selected; });
    }));
    document.getElementById("refreshButton").addEventListener("click", loadAll);
    document.getElementById("reportButton").addEventListener("click", loadMappingReport);
    document.getElementById("modelProposalForm").addEventListener("submit", submitModelProposal);
    document.getElementById("copyOwnershipScript").addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(ownershipScript.value); setStatus("Remediation SQL copied for review; it has not been applied."); }
        catch { setStatus("Clipboard access unavailable. The read-only generated script remains visible for review.", true); }
    });
    document.getElementById("copyOwnershipRollbackScript").addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(ownershipRollbackScript.value); setStatus("Rollback SQL copied for review; no remediation has been applied."); }
        catch { setStatus("Clipboard access unavailable. The generated rollback script remains visible for review.", true); }
    });
    async function downloadReviewPackage(path, filename) {
        try {
            const payload = await request(path);
            const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
            const link = document.createElement("a");
            link.href = url;
            link.download = filename;
            link.click();
            URL.revokeObjectURL(url);
            setStatus(`${filename} exported. It is a read-only review package; no database changes were made.`);
        } catch (error) { setStatus(error.message, true); }
    }
    document.getElementById("exportOwnershipPackage").addEventListener("click", () =>
        downloadReviewPackage("/operations/ownership-remediation/approval-package", "ownership-remediation-review.json"));
    document.getElementById("exportOwnershipDocument").addEventListener("click", async () => {
        try {
            const payload = await request("/operations/ownership-remediation/approval-document");
            const url = URL.createObjectURL(new Blob([payload.document], { type: payload.content_type || "text/markdown" }));
            const link = document.createElement("a");
            link.href = url;
            link.download = payload.filename || "ownership-remediation-approval.md";
            link.click();
            URL.revokeObjectURL(url);
            setStatus("Approval document exported for review. No ownership data was changed.");
        } catch (error) { setStatus(error.message, true); }
    });
    document.getElementById("exportRlsPackage").addEventListener("click", () =>
        downloadReviewPackage("/operations/rls-readiness/package", "rls-readiness-review.json"));
    document.getElementById("downloadActivationRunbook").addEventListener("click", () =>
        downloadReviewPackage("/operations/activation-runbook", "operational-activation-runbook.json"));
    document.getElementById("downloadRollbackPackage").addEventListener("click", () =>
        downloadReviewPackage("/operations/ownership-remediation/rollback-package", "ownership-rollback-review.json"));
    document.getElementById("downloadOwnershipAudit").addEventListener("click", () =>
        downloadReviewPackage("/operations/ownership-remediation/audit-package", "ownership-review-audit.json"));
    document.getElementById("downloadMigrationDryRun").addEventListener("click", () => {
        if (migration24Report) downloadJson(migration24Report, "migration-24-static-validation.json");
    });
    document.getElementById("downloadModelOnboarding").addEventListener("click", () => {
        if (modelOnboardingPackage) downloadJson(modelOnboardingPackage, "model-onboarding-review.json");
    });
    document.getElementById("downloadModelEvidence").addEventListener("click", () =>
        downloadReviewPackage("/operations/model-onboarding/approval-evidence-package", "model-approval-evidence.json"));
    document.getElementById("downloadPhase11Package").addEventListener("click", () => {
        if (phase11DeploymentPackage) downloadJson(phase11DeploymentPackage, "phase-11-deployment-readiness.json");
    });
    document.getElementById("downloadPhase12Package").addEventListener("click", () =>
        downloadReviewPackage("/operations/phase12-activation-readiness", "phase-12-operational-activation-readiness.json"));
    document.getElementById("downloadPhase13Package").addEventListener("click", () =>
        downloadReviewPackage("/operations/phase13-pilot-preparation", "phase-13-controlled-pilot-preparation.json"));
    document.getElementById("downloadPhase14Package").addEventListener("click", () =>
        downloadReviewPackage("/operations/phase14-execution-planning", "phase-14-controlled-pilot-execution-plan.json"));
    document.getElementById("downloadPhase15Package").addEventListener("click", () =>
        downloadReviewPackage("/operations/phase15-governance-evidence", "phase-15-pilot-governance-evidence.json"));
    document.getElementById("downloadPhase16Package").addEventListener("click", () =>
        downloadReviewPackage("/operations/phase16-authorization-readiness", "phase-16-pilot-authorization-readiness.json"));
    document.getElementById("downloadAIGovernanceShadowReview").addEventListener("click", () =>
        downloadReviewPackage("/operations/ai-governance/shadow-review", "ai-governance-shadow-review.json"));
    document.getElementById("downloadGovernanceAssurance").addEventListener("click", () =>
        downloadReviewPackage("/operations/ai-governance/assurance-platform", "governance-assurance-platform.json"));
    document.getElementById("downloadPhase17Package").addEventListener("click", () =>
        downloadReviewPackage("/operations/phase17-operational-tracking", "phase-17-operational-execution-tracking.json"));
    document.getElementById("downloadGovernanceCommandCenter").addEventListener("click", () =>
        downloadReviewPackage("/operations/governance-command-center", "unified-governance-command-center.json"));
    document.getElementById("downloadUatReadiness").addEventListener("click", () =>
        downloadReviewPackage("/operations/uat-readiness", "uat-readiness-traceability-package.json"));
    document.getElementById("ownershipReviewForm").addEventListener("submit", async event => {
        event.preventDefault();
        const button = event.currentTarget.querySelector("button[type='submit']");
        button.disabled = true;
        try {
            const result = await request("/operations/ownership-remediation/reviews", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    decision: document.getElementById("ownershipReviewDecision").value,
                    change_ticket: document.getElementById("ownershipReviewTicket").value.trim(),
                    reason: document.getElementById("ownershipReviewReason").value.trim(),
                    evidence: document.getElementById("ownershipReviewEvidence").value.trim(),
                }),
            });
            setStatus(`Review decision recorded in audit. Ownership SQL executed: ${result.ownership_sql_executed}. Ownership records changed: ${result.ownership_records_changed}.`);
            await loadOperationsDashboard();
        } catch (error) { setStatus(error.message, true); }
        finally { button.disabled = false; }
    });
    document.getElementById("phase11ModelProposalForm").addEventListener("submit", async event => {
        event.preventDefault();
        const button = event.currentTarget.querySelector("button[type='submit']");
        button.disabled = true;
        try {
            const payload = {
                provider: document.getElementById("phase11ProposalProvider").value,
                model: document.getElementById("phase11ProposalModel").value.trim(),
                version: document.getElementById("phase11ProposalVersion").value.trim(),
                reason: document.getElementById("phase11ProposalReason").value.trim(),
                evidence: document.getElementById("phase11ProposalEvidence").value.trim(),
            };
            const result = await request("/governance/models/proposals", {
                method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
            });
            setStatus(`Model proposal created as ${result.status}. It is not approved, configured on an agent, or enabled for runtime.`);
            event.currentTarget.reset();
            await loadOperationsDashboard();
            await loadGovernanceData();
        } catch (error) { setStatus(error.message, true); }
        finally { button.disabled = false; }
    });
    function downloadJson(payload, filename) {
        const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(url);
        setStatus(`${filename} exported. No migration, model approval, activation, or ownership correction was executed.`);
    }
    document.getElementById("executiveReadinessView").addEventListener("change", event => renderExecutiveReadinessView(event.currentTarget.value));
    loadAll();
})();

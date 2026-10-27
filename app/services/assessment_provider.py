from abc import ABC, abstractmethod


class DeterministicAssessmentProvider:
    """Offline/demo assessment rules; this is not an LLM or production decision engine."""

    def assess(self, requirement):
        request_text = f"{requirement.Title} {requirement.Description}".lower()
        if self._is_hr_onboarding(request_text):
            return self._assess_hr_onboarding()
        return self._assess_supplier_compliance(request_text)

    @staticmethod
    def _is_hr_onboarding(request_text):
        hr_context = any(term in request_text for term in ("human resources", "employee", "new hire", "hr "))
        onboarding_context = any(term in request_text for term in ("onboarding", "on-boarding", "preboarding"))
        return hr_context and onboarding_context

    @staticmethod
    def _assess_hr_onboarding():
        departments = [
            {
                "department_name": "HR",
                "responsibility": "Own onboarding policy, checklist, and employee data minimization.",
                "is_lead_department": True,
                "priority": "High",
            },
            {
                "department_name": "Technology",
                "responsibility": "Assess HRIS and identity integration boundaries and provisioning controls.",
                "is_lead_department": False,
                "priority": "High",
            },
            {
                "department_name": "Cybersecurity",
                "responsibility": "Review least privilege, audit, retention, and account provisioning safeguards.",
                "is_lead_department": False,
                "priority": "High",
            },
            {
                "department_name": "PMO",
                "responsibility": "Coordinate the pilot plan, dependencies, and delivery governance.",
                "is_lead_department": False,
                "priority": "Medium",
            },
        ]
        skills = [
            {
                "skill_name": "RequirementAnalysis",
                "priority": "High",
                "minimum_proficiency": 4,
                "purpose": "Confirm employee, manager, HR, and IT onboarding journeys and acceptance criteria.",
                "estimated_effort_hours": 32,
                "is_mandatory": True,
            },
            {
                "skill_name": "ProjectPlanning",
                "priority": "High",
                "minimum_proficiency": 4,
                "purpose": "Plan a controlled pilot, dependencies, and release gates.",
                "estimated_effort_hours": 24,
                "is_mandatory": True,
            },
            {
                "skill_name": "SecurityReview",
                "priority": "High",
                "minimum_proficiency": 4,
                "purpose": "Review employee-data access, retention, audit, and provisioning safeguards.",
                "estimated_effort_hours": 24,
                "is_mandatory": True,
            },
        ]
        return {
            "classification": "HR Employee Onboarding Workflow",
            "business_domain": "Human Resources",
            "complexity": "High",
            "risk_level": "High",
            "feasibility": "FeasibleWithConditions",
            "feasibility_score": 78,
            "confidence_score": 72,
            "executive_summary": (
                "A role-scoped onboarding workflow is feasible after the HRIS, identity provider, "
                "jurisdictions, retention schedule, and accountable approval owners are confirmed. "
                "Account provisioning, employee communications, and production activation must remain "
                "behind explicit human approval gates."
            ),
            "departments": departments,
            "required_skills": skills,
            "risks": [
                {
                    "title": "Unauthorized account provisioning",
                    "risk_level": "Critical",
                    "description": "Premature automation could grant employee access before authorization is verified.",
                    "mitigation": "Require an approved hire, explicit HR authorization, least-privilege policies, and auditable provisioning gates.",
                },
                {
                    "title": "Excessive employee data collection",
                    "risk_level": "High",
                    "description": "Onboarding workflows can collect more sensitive employee information than needed.",
                    "mitigation": "Minimize data fields, exclude secrets and sensitive identity records, and confirm retention/jurisdiction rules before launch.",
                },
            ],
            "assumptions": [
                "An authoritative HRIS and identity provider will be selected.",
                "Hiring and employment decisions remain with authorized people.",
            ],
            "constraints": [
                "Do not collect passwords, banking, health, or identity-document data in the onboarding workflow.",
                "Production account provisioning requires separate authorized approval.",
                "Jurisdiction-specific retention and employment requirements need legal/privacy confirmation.",
            ],
            "human_approval_required": True,
        }

    @staticmethod
    def _assess_supplier_compliance(request_text):
        departments = [{
            "department_name": "PMO",
            "responsibility": "Govern planning, dependencies and delivery.",
            "is_lead_department": True,
            "priority": "High",
        }]
        mapping = {
            "Procurement": ["supplier", "vendor", "procurement"],
            "Data & Analytics": ["sql", "power bi", "analytics", "dashboard"],
            "Technology": ["system", "platform", "api", "sharepoint"],
            "Cybersecurity": ["security", "role-based"],
            "Legal & Compliance": ["compliance"],
            "Quality": ["quality", "audit"],
        }
        for name, terms in mapping.items():
            if any(term in request_text for term in terms):
                departments.append({
                    "department_name": name,
                    "responsibility": f"Provide {name} governance and delivery support.",
                    "is_lead_department": False,
                    "priority": "High" if name in {"Procurement", "Technology", "Data & Analytics"} else "Medium",
                })

        skills = [
            {"skill_name": name, "priority": "High", "minimum_proficiency": 4, "purpose": purpose, "estimated_effort_hours": hours, "is_mandatory": True}
            for name, purpose, hours in [
                ("RequirementAnalysis", "Structure business requirements", 40),
                ("ProjectPlanning", "Create governed delivery plan", 24),
                ("SQLDevelopment", "Implement SQL data layer", 80),
                ("PowerBIDevelopment", "Create dashboards", 60),
                ("SecurityReview", "Review security controls", 24),
            ]
        ]
        return {
            "classification": "Enterprise Business Application",
            "business_domain": "Supplier Compliance",
            "complexity": "High",
            "risk_level": "Medium",
            "feasibility": "FeasibleWithConditions",
            "feasibility_score": 85,
            "confidence_score": 90,
            "executive_summary": "The requirement is feasible with a governed implementation plan and human review.",
            "departments": departments,
            "required_skills": skills,
            "risks": [{"title": "Supplier document quality", "risk_level": "Medium", "description": "Documents may be missing, expired or inconsistent.", "mitigation": "Use validation, expiry monitoring and approval controls."}],
            "assumptions": ["Required platform connectivity is available."],
            "constraints": ["Production deployment requires approval."],
            "human_approval_required": True,
        }


class AssessmentProvider(ABC):
    @abstractmethod
    def assess(self, requirement):
        raise NotImplementedError
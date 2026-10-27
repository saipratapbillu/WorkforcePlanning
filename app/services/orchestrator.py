DEPT_RULES = {
    "supplier": ["PMO","Procurement","Technology","Data & Analytics","Cybersecurity","Legal & Compliance","Quality"],
    "power bi": ["Data & Analytics","Technology","Cybersecurity"],
    "sharepoint": ["Technology","Cybersecurity","Data & Analytics"],
    "finance": ["Finance","Risk","Legal & Compliance","Cybersecurity"],
}

def classify_requirement(text: str):
    t = text.lower()
    departments = {"PMO", "Technology"}
    for key, values in DEPT_RULES.items():
        if key in t:
            departments.update(values)
    risk = "High" if any(x in t for x in ["production","sensitive","payroll","contract","payment"]) else "Medium"
    return {"departments": sorted(departments), "risk_level": risk, "human_approval_required": risk == "High"}

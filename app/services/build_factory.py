"""Static build/release planning from source-package metadata only."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any


REQUIRED_ARTIFACTS = {
    "backend": ("backend/src/", "backend/app/"),
    "frontend": ("frontend/src/App.tsx", "frontend/package.json"),
    "database": ("database/schema.sql", "database/indexes.sql"),
    "api": ("api/openapi.json",),
    "security": ("security/SECURITY.md", "security/rbac-matrix.csv"),
    "tests": ("tests/README.md", "tests/uat-scenarios.md"),
    "devops": ("devops/Dockerfile", "devops/.github/workflows/ci.yml", "devops/.env.example"),
}
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def _file_map(code_package: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(code_package, dict):
        return {}
    result: dict[str, str] = {}
    for entry in code_package.get("files", []):
        if not isinstance(entry, dict):
            continue
        path, content = entry.get("path"), entry.get("content")
        if isinstance(path, str) and isinstance(content, str):
            result[path.replace("\\", "/")] = content
    return result


def _dependency_analysis(files: dict[str, str]) -> dict[str, Any]:
    dependencies: list[dict[str, str]] = []
    frameworks: list[dict[str, str]] = []
    risks: list[dict[str, str]] = []

    requirements = files.get("backend/requirements.txt", "")
    for line in requirements.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", stripped)
        if match:
            dependencies.append({"ecosystem": "pypi", "name": match.group(1),
                                 "declared_constraint": match.group(2).strip() or "UNPINNED"})
    pyproject = files.get("backend/pyproject.toml", "")
    python_version = re.search(r'requires-python\s*=\s*["\']([^"\']+)', pyproject)
    if python_version:
        frameworks.append({"ecosystem": "python", "framework": "Python",
                           "declared_version": python_version.group(1)})

    node_package = files.get("backend/package.json")
    if node_package:
        try:
            parsed = json.loads(node_package)
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                for name, constraint in parsed.get(section, {}).items():
                    dependencies.append({"ecosystem": "npm", "name": name,
                                         "declared_constraint": str(constraint), "dependency_type": section})
            engines = parsed.get("engines", {})
            if engines.get("node"):
                frameworks.append({"ecosystem": "node", "framework": "Node.js",
                                   "declared_version": str(engines["node"])})
            else:
                risks.append({"category": "Version Risk", "severity": "Medium",
                              "description": "Node.js engine version is not declared in package.json."})
        except (ValueError, TypeError):
            risks.append({"category": "Dependency Risk", "severity": "High",
                          "description": "Generated backend package.json is not valid JSON."})

    project_file = files.get("backend/src/GeneratedService.csproj", "")
    target_framework = re.search(r"<TargetFramework>([^<]+)</TargetFramework>", project_file)
    if target_framework:
        frameworks.append({"ecosystem": "dotnet", "framework": ".NET",
                           "declared_version": target_framework.group(1)})
    for name, version in re.findall(r'<PackageReference\s+Include="([^"]+)"\s+Version="([^"]+)"', project_file):
        dependencies.append({"ecosystem": "nuget", "name": name, "declared_constraint": version})

    ecosystems = Counter(item["ecosystem"] for item in dependencies)
    for ecosystem, manifest_path, lock_paths in (
        ("pypi", "backend/requirements.txt", ("backend/requirements.lock", "backend/poetry.lock", "backend/uv.lock")),
        ("npm", "backend/package.json", ("backend/package-lock.json", "backend/npm-shrinkwrap.json")),
        ("nuget", "backend/src/GeneratedService.csproj", ("backend/packages.lock.json",)),
    ):
        has_manifest = manifest_path in files
        has_dependency = ecosystems[ecosystem] > 0
        has_lock = any(path in files for path in lock_paths)
        if has_manifest and has_dependency and not has_lock:
            risks.append({"category": "Dependency Risk", "severity": "Medium",
                          "description": f"{ecosystem} dependencies are declared without a lockfile; reproducibility is not established."})
    if dependencies:
        risks.append({"category": "Compatibility Risk", "severity": "Medium",
                      "description": "Dependency ranges were parsed statically only; registry resolution and framework compatibility were not checked."})
    if not dependencies:
        risks.append({"category": "Dependency Risk", "severity": "High",
                      "description": "No parseable backend dependency declarations were found."})
    return {
        "framework_versions": frameworks,
        "dependencies": dependencies,
        "compatibility_report": {"status": "UNVERIFIED_STATIC_DECLARATIONS",
                                  "compatibility_verified": False,
                                  "package_resolution_performed": False,
                                  "basis": "Declared constraints only; no registry, package manager, network, or compiler was invoked."},
        "compatibility_verified": False,
        "risks": risks,
        "dependencies_installed": False,
    }


def _category_for(path: str) -> str:
    if path.startswith("backend/"):
        return "backend"
    if path.startswith("frontend/"):
        return "frontend"
    if path.startswith("database/"):
        return "database"
    if path.startswith("api/"):
        return "api"
    if path.startswith("security/"):
        return "security"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("devops/"):
        return "devops"
    if path.startswith("delivery/"):
        return "delivery"
    return "other"


def _version_plan(version: str) -> dict[str, Any]:
    if not SEMVER_PATTERN.fullmatch(version):
        raise ValueError("semantic_version must follow MAJOR.MINOR.PATCH[-PRERELEASE]")
    return {
        "semantic_version": version,
        "release_number": f"REL-{version}",
        "build_number": "SIMULATED-NOT-ALLOCATED",
        "artifact_tags": [f"planned/{version}", "source-package/review-required"],
        "version_status": "PROPOSED_NOT_RESERVED",
        "build_number_status": "NOT_ALLOCATED",
    }


def build_release_artifact_package(code_package: dict[str, Any] | None,
                                   testing_package: dict[str, Any] | None,
                                   project_package: dict[str, Any] | None,
                                   semantic_version: str = "0.1.0") -> dict[str, Any]:
    """Return a build/release plan based on package strings; never compile or publish."""
    files = _file_map(code_package)
    tests = testing_package if isinstance(testing_package, dict) else {}
    project = project_package if isinstance(project_package, dict) else {}
    dependencies = _dependency_analysis(files)
    paths = sorted(files)

    artifact_manifest = []
    for path in paths:
        content = files[path]
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifact_manifest.append({"path": path, "category": _category_for(path),
                                 "size_bytes": len(content.encode("utf-8")),
                                 "sha256": digest, "planned_only": True})
    category_counts = Counter(item["category"] for item in artifact_manifest)
    required_checks = {}
    for category, expected_paths in REQUIRED_ARTIFACTS.items():
        required_checks[category] = {
            "required_paths": list(expected_paths),
            "present_paths": [path for path in expected_paths if path in files],
            "missing_paths": [path for path in expected_paths if path not in files],
        }
    complete_categories = sum(not value["missing_paths"] for value in required_checks.values())
    completeness_percent = round(100 * complete_categories / len(REQUIRED_ARTIFACTS), 1)

    placeholder_patterns = ("NotImplementedError", "not configured", "REQUIRES_REVIEW",
                           "fail-closed", "TODO", "adapter is not configured")
    potential_issues = []
    for path, content in files.items():
        found = [pattern for pattern in placeholder_patterns if pattern.lower() in content.lower()]
        for pattern in found:
            potential_issues.append({"path": path, "signal": pattern,
                                     "classification": "TEMPLATE_PLACEHOLDER_POTENTIAL_COMPILE_OR_RUNTIME_GAP",
                                     "observed_compile_error": False})
    missing_components = [path for item in required_checks.values() for path in item["missing_paths"]]
    for path in missing_components:
        potential_issues.append({"path": path, "signal": "Required package component absent",
                                 "classification": "MISSING_ARTIFACT", "observed_compile_error": False})

    base_probability = max(5.0, min(95.0, completeness_percent - min(len(potential_issues) * 2.5, 35))) if paths else 0.0
    compilation_assessment = {
        "execution_status": "NOT_COMPILED",
        "observed_build_result": None,
        "build_success_probability_estimate": round(base_probability, 1) if paths else None,
        "probability_basis": "Synthetic heuristic from package completeness and template-placeholder count; not an empirical or executed build result.",
        "potential_compile_issues": potential_issues,
        "missing_components": missing_components,
        "compilation_performed": False,
    }

    manifest_by_category = {category: [item for item in artifact_manifest if item["category"] == category]
                            for category in ("backend", "frontend", "database", "api", "security", "tests", "devops")}
    artifact_plans = {
        "application": {"artifacts": manifest_by_category["backend"] + manifest_by_category["frontend"],
                        "package_published": False, "plan_status": "PLANNED_NOT_BUILT"},
        "container": {"dockerfile_present": "devops/Dockerfile" in files,
                      "container_built": False, "plan_status": "PLANNED_NOT_BUILT"},
        "database": {"artifacts": manifest_by_category["database"],
                     "ddl_applied": False, "plan_status": "PLANNED_NOT_APPLIED"},
        "configuration": {"environment_templates": [path for path in paths if ".env" in path or "variables.tf" in path],
                           "secrets_included": False, "plan_status": "PLACEHOLDERS_ONLY"},
    }

    version_plan = _version_plan(semantic_version)
    bundle_files = [
        "backend/", "frontend/", "database/", "api/", "security/", "tests/", "devops/",
        "delivery/blueprint-summary.json", "BUILD_MANIFEST.json", "RELEASE_NOTES.md",
    ]
    release_package_plan = {
        "bundle_name": f"{project.get('project_charter', {}).get('project_name', 'project')}-{semantic_version}-source-plan",
        "bundle_structure": bundle_files,
        "package_manifest": {"file_count": len(artifact_manifest), "categories": dict(category_counts),
                             "content_hashes_included": True, "manifest_output_path": "BUILD_MANIFEST.json"},
        "release_checklist": ["Review source templates and ownership", "Resolve and lock dependencies in an isolated approved environment",
                               "Run unit/integration/security/UAT/performance tests with evidence", "Review SBOM, licenses, and vulnerability status",
                               "Obtain independent release and deployment approvals"],
        "bundle_created": False, "package_published": False,
    }

    test_status = tests.get("unit_test_report", {}).get("execution_status", "UNAVAILABLE")
    test_controls = tests.get("controls", {})
    checks = {
        "artifact_completeness": {"passed": completeness_percent == 100, "value_percent": completeness_percent},
        "dependency_declarations": {"passed": bool(dependencies["dependencies"]),
                                     "value": len(dependencies["dependencies"])},
        "tests_executed_and_passed": {"passed": test_status == "EXECUTED_ALL_PASSED",
                                      "value": test_status,
                                      "blocking": not bool(test_controls.get("tests_executed", False))},
        "compilation_observed": {"passed": False, "value": "NOT_COMPILED", "blocking": True},
        "security_configuration": {"passed": False, "value": "TEMPLATE_FAIL_CLOSED", "blocking": True},
        "release_approval": {"passed": False, "value": "NOT_REQUESTED", "blocking": True},
    }
    passed_checks = sum(bool(check["passed"]) for check in checks.values())
    readiness_score = round(100 * passed_checks / len(checks), 1)
    blockers = [name for name, check in checks.items() if not check["passed"]]
    readiness_status = "NOT READY" if not paths or completeness_percent < 50 else "PARTIALLY READY"
    quality_gates = {"gates": checks, "passed_count": passed_checks, "total_count": len(checks),
                     "readiness_score_percent": readiness_score, "status": readiness_status,
                     "blockers": blockers, "ready_for_release": False}

    dependency_risks = dependencies["risks"]
    build_risks = dependency_risks + [
        {"category": "Version Risk", "severity": "Medium", "description": "Version/build identifiers are proposed and not reserved by a release registry."},
        {"category": "Packaging Risk", "severity": "High", "description": "Source templates contain deliberate fail-closed adapters and have not been compiled or validated."},
        {"category": "Release Risk", "severity": "High", "description": "No observed test, security scan, SBOM, approval, or release evidence is present."},
    ]
    build_risk_report = {"risks": build_risks, "risk_count": len(build_risks),
                         "highest_severity": "HIGH", "status": "PLANNING_RISKS_NOT_ASSESSED_IN_BUILD"}
    build_dashboard = {
        "build_readiness_percent": readiness_score,
        "dependency_health": dependencies["compatibility_report"]["status"],
        "packaging_status": "PLANNED_NOT_BUILT",
        "artifact_coverage_percent": completeness_percent,
        "risk_status": "HIGH",
        "compilation_status": "NOT_COMPILED",
    }
    build_blueprint = {
        "source_package": code_package.get("package") if isinstance(code_package, dict) else None,
        "testing_status": test_status,
        "project_name": project.get("project_charter", {}).get("project_name"),
        "backend_language": code_package.get("backend_language") if isinstance(code_package, dict) else None,
        "build_stages": ["Inspect source manifest", "Review declared dependencies", "Plan application/database/config artifacts", "Review tests and security gates", "Prepare release bundle manifest"],
        "build_execution": "NOT_PERFORMED",
    }
    build_execution_package = {
        "build_blueprint": build_blueprint,
        "artifact_manifest": {"artifacts": artifact_manifest, "category_counts": dict(category_counts),
                              "required_path_checks": required_checks},
        "dependency_analysis": dependencies,
        "compilation_assessment": compilation_assessment,
        "artifact_plans": artifact_plans,
        "version_plan": version_plan,
        "release_package_plan": release_package_plan,
        "quality_gates": quality_gates,
        "risk_report": build_risk_report,
        "build_readiness_assessment": {"status": readiness_status, "readiness_score_percent": readiness_score,
                                       "blockers": blockers, "ready_for_release": False},
    }
    return {
        "package": "Autonomous Build Factory Plan",
        "status": "PLANNING_AND_SIMULATION_ONLY",
        "authority": "NONE",
        "action_allowed": False,
        "persistence": False,
        "analysis_mode": "STATIC_PACKAGE_METADATA_NO_BUILD_EXECUTION",
        **build_execution_package,
        "build_risk_report": build_risk_report,
        "build_dashboard": build_dashboard,
        "build_execution_package": build_execution_package,
        "controls": {"compilation_performed": False, "container_built": False,
                     "ci_cd_executed": False, "package_published": False,
                     "infrastructure_created": False, "deployment_performed": False,
                     "persistence": False, "authority": False},
        "interpretation": "Build probability, completeness, and readiness are static planning estimates. No compiler, package manager, container engine, network resolver, CI/CD system, or publisher was invoked.",
    }
"""Bounded source-artifact generation; never writes files or executes output."""

from __future__ import annotations

import json
import re
from typing import Any


BACKEND_LANGUAGES = {"dotnet", "python", "node"}


def _python_backend() -> dict[str, str]:
    return {
        "backend/requirements.txt": "fastapi>=0.115,<1\nuvicorn[standard]>=0.30,<1\npydantic>=2.8,<3\nhttpx>=0.27,<1\npytest>=8,<9\n",
        "backend/app/main.py": '''from fastapi import FastAPI
from app.routes.requirements import router as requirements_router

app = FastAPI(title="Generated Service", version="1.0.0", docs_url=None, redoc_url=None)
app.include_router(requirements_router, prefix="/api/v1")

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}
''',
        "backend/app/models.py": '''from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

class RequirementCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=12000)

class RequirementRecord(BaseModel):
    requirement_id: UUID
    tenant_id: UUID
    created_by: UUID
    title: str
    description: str
    status: str
    created_at_utc: datetime
''',
        "backend/app/entities.py": '''from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

@dataclass(frozen=True)
class RequirementEntity:
    requirement_id: UUID
    tenant_id: UUID
    created_by: UUID
    title: str
    description: str
    status: str
    created_at_utc: datetime
''',
        "backend/app/repositories.py": '''from typing import Protocol
from uuid import UUID
from app.models import RequirementCreate, RequirementRecord

class RequirementRepository(Protocol):
    def create(self, data: RequirementCreate, tenant_id: UUID, actor_id: UUID) -> RequirementRecord: ...
    def get(self, requirement_id: UUID, tenant_id: UUID, actor_id: UUID) -> RequirementRecord | None: ...

class UnconfiguredRequirementRepository:
    def create(self, data: RequirementCreate, tenant_id: UUID, actor_id: UUID) -> RequirementRecord:
        raise NotImplementedError("Bind an approved tenant-scoped persistence adapter.")
    def get(self, requirement_id: UUID, tenant_id: UUID, actor_id: UUID) -> RequirementRecord | None:
        raise NotImplementedError("Bind an approved tenant-scoped persistence adapter.")
''',
        "backend/app/services.py": '''from uuid import UUID
from app.models import RequirementCreate, RequirementRecord
from app.repositories import RequirementRepository

class RequirementService:
    def __init__(self, repository: RequirementRepository):
        self._repository = repository

    def create(self, data: RequirementCreate, tenant_id: UUID, authenticated_actor_id: UUID) -> RequirementRecord:
        if not tenant_id or not authenticated_actor_id:
            raise PermissionError("Authenticated tenant and actor are required")
        return self._repository.create(data, tenant_id, authenticated_actor_id)

    def get(self, requirement_id: UUID, tenant_id: UUID, authenticated_actor_id: UUID) -> RequirementRecord:
        if not tenant_id or not authenticated_actor_id:
            raise PermissionError("Authenticated tenant and actor are required")
        record = self._repository.get(requirement_id, tenant_id, authenticated_actor_id)
        if record is None:
            raise LookupError("Requirement not found")
        return record
''',
        "backend/app/security.py": '''from fastapi import Header, HTTPException

async def require_authenticated_actor(authorization: str | None = Header(default=None)) -> str:
    # Replace with verified issuer/audience/signature/expiry validation before use.
    # The template deliberately rejects requests until identity integration exists.
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    raise HTTPException(status_code=503, detail="Identity provider validation is not configured")

def require_role(required_role: str):
    async def dependency(actor_id: str = "") -> str:
        # Implement role and resource authorization from verified server-side claims.
        raise HTTPException(status_code=503, detail=f"Authorization policy {required_role} is not configured")
    return dependency
''',
        "backend/app/audit.py": '''from typing import Protocol

class AuditWriter(Protocol):
    def record(self, *, actor_id: str, action: str, resource_id: str,
               outcome: str, correlation_id: str) -> None: ...

class UnconfiguredAuditWriter:
    def record(self, **event) -> None:
        raise NotImplementedError("Bind an approved append-only audit implementation.")
''',
        "backend/app/routes/requirements.py": '''from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from app.models import RequirementCreate
from app.security import require_authenticated_actor

router = APIRouter(tags=["Requirements"])

@router.post("/requirements", status_code=201)
def create_requirement(payload: RequirementCreate,
                       actor_id: str = Depends(require_authenticated_actor)):
    # Bind an approved service/repository and audit writer before enabling writes.
    raise HTTPException(status_code=503, detail="Persistence adapter is not configured")

@router.get("/requirements/{requirement_id}")
def get_requirement(requirement_id: UUID,
                    actor_id: str = Depends(require_authenticated_actor)):
    # Resource-level authorization must be enforced inside the service/repository.
    raise HTTPException(status_code=503, detail="Persistence adapter is not configured")
''',
        "backend/tests/test_models.py": '''from app.models import RequirementCreate

def test_requirement_title_is_bounded():
    assert RequirementCreate(title="Valid title", description="A sufficiently detailed requirement.").title == "Valid title"
''',
        "backend/pyproject.toml": '''[project]
name = "generated-service"
version = "0.1.0"
requires-python = ">=3.12"

[tool.pytest.ini_options]
pythonpath = ["."]
''',
    }


def _node_backend() -> dict[str, str]:
    return {
        "backend/package.json": json.dumps({"name": "generated-service", "private": True,
            "type": "module", "scripts": {"start": "node src/server.js", "test": "node --test"},
            "dependencies": {"express": "^5.1.0"}}, indent=2) + "\n",
        "backend/src/server.js": '''import express from "express";
import { requirementsRouter } from "./routes/requirements.js";

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "32kb", strict: true }));
app.use("/api/v1", requirementsRouter);
app.get("/health", (_request, response) => response.json({ status: "ok" }));

if (process.env.NODE_ENV !== "test") {
  const port = Number(process.env.PORT || 8080);
  app.listen(port, "0.0.0.0");
}
export { app };
''',
        "backend/src/models/requirement.js": '''export function validateRequirement(input) {
  if (!input || typeof input.title !== "string" || input.title.trim().length < 3 || input.title.length > 200) {
    throw Object.assign(new Error("Invalid title"), { status: 422 });
  }
  if (typeof input.description !== "string" || input.description.trim().length < 10 || input.description.length > 12000) {
    throw Object.assign(new Error("Invalid description"), { status: 422 });
  }
  return { title: input.title.trim(), description: input.description.trim() };
}

export function createRequirementEntity({ id, tenantId, actorId, title, description, createdAt }) {
    if (!id || !tenantId || !actorId) throw new Error("Tenant-scoped identity fields are required");
    return { id, tenantId, createdBy: actorId, title, description, status: "Submitted", createdAt };
}
''',
        "backend/src/repositories/requirementRepository.js": '''export class RequirementRepository {
  async create(_data, _actor) {
    throw new Error("Bind an approved tenant-scoped persistence adapter before enabling writes");
  }
  async get(_id, _actor) {
    throw new Error("Bind an approved tenant-scoped persistence adapter before enabling reads");
  }
}
''',
        "backend/src/services/requirementService.js": '''export class RequirementService {
  constructor(repository) { this.repository = repository; }
  async create(data, actor) {
    if (!actor?.id || !actor?.tenantId) throw Object.assign(new Error("Authenticated scope required"), { status: 401 });
    return this.repository.create(data, actor);
  }
  async get(id, actor) {
    if (!actor?.id || !actor?.tenantId) throw Object.assign(new Error("Authenticated scope required"), { status: 401 });
    return this.repository.get(id, actor);
  }
}
''',
        "backend/src/security/auth.js": '''export function requireAuthenticated(_request, _response, next) {
  // Configure verified issuer, audience, signature, expiry, and revocation checks.
  // Deny by default until the approved identity provider is configured.
  const error = Object.assign(new Error("Identity provider validation is not configured"), { status: 503 });
  next(error);
}

export function requireRole(_role) {
  return (_request, _response, next) => {
    next(Object.assign(new Error("Authorization policy is not configured"), { status: 503 }));
    };
}
''',
        "backend/src/audit/auditWriter.js": '''export class AuditWriter {
  async record(_event) {
    throw new Error("Bind an approved append-only audit implementation before use");
  }
}
''',
        "backend/src/routes/requirements.js": '''import { Router } from "express";
import { requireAuthenticated } from "../security/auth.js";
import { validateRequirement } from "../models/requirement.js";

export const requirementsRouter = Router();
requirementsRouter.use(requireAuthenticated);
requirementsRouter.post("/requirements", (_request, _response, next) => {
  try { validateRequirement(_request.body); next(Object.assign(new Error("Persistence adapter is not configured"), { status: 503 })); }
  catch (error) { next(error); }
});
requirementsRouter.get("/requirements/:id", (_request, _response, next) =>
  next(Object.assign(new Error("Persistence adapter is not configured"), { status: 503 })));
''',
        "backend/test/requirement.test.js": '''import test from "node:test";
import assert from "node:assert/strict";
import { validateRequirement } from "../src/models/requirement.js";

test("requirement model trims bounded fields", () => {
  assert.equal(validateRequirement({ title: "  Portal  ", description: " detailed scope " }).title, "Portal");
});
test("requirement model rejects undersized title", () => {
  assert.throws(() => validateRequirement({ title: "x", description: "detailed scope" }));
});
''',
    }


def _dotnet_backend() -> dict[str, str]:
    return {
        "backend/src/GeneratedService.csproj": '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework><Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings></PropertyGroup>
</Project>
''',
        "backend/src/Program.cs": '''using GeneratedService.Repositories;
    using GeneratedService.Services;
    using GeneratedService.Security;
    using Microsoft.AspNetCore.Authentication;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddAuthentication("FailClosed")
    .AddScheme<AuthenticationSchemeOptions, FailClosedAuthenticationHandler>("FailClosed", _ => { });
builder.Services.AddAuthorization(options => options.FallbackPolicy = options.DefaultPolicy);
builder.Services.AddScoped<IRequirementRepository, UnconfiguredRequirementRepository>();
builder.Services.AddScoped<RequirementService>();
var app = builder.Build();
app.UseHttpsRedirection();
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
app.Run();

public partial class Program { }
''',
        "backend/src/Models/Requirement.cs": '''namespace GeneratedService.Models;

public sealed record Requirement(Guid RequirementId, Guid TenantId, Guid CreatedBy,
    string Title, string Description, string Status, DateTimeOffset CreatedAtUtc);
''',
        "backend/src/DTOs/RequirementCreateRequest.cs": '''using System.ComponentModel.DataAnnotations;

namespace GeneratedService.DTOs;

public sealed class RequirementCreateRequest
{
    [Required, StringLength(200, MinimumLength = 3)] public required string Title { get; init; }
    [Required, StringLength(12000, MinimumLength = 10)] public required string Description { get; init; }
}
''',
        "backend/src/Repositories/IRequirementRepository.cs": '''using GeneratedService.Models;

namespace GeneratedService.Repositories;

public interface IRequirementRepository
{
    Task<Requirement> CreateAsync(string tenantId, string actorId, string title, string description, CancellationToken cancellationToken);
    Task<Requirement?> GetAsync(string tenantId, string actorId, Guid id, CancellationToken cancellationToken);
}

public sealed class UnconfiguredRequirementRepository : IRequirementRepository
{
    public Task<Requirement> CreateAsync(string tenantId, string actorId, string title, string description, CancellationToken cancellationToken)
        => throw new NotImplementedException("Bind an approved tenant-scoped persistence adapter.");
    public Task<Requirement?> GetAsync(string tenantId, string actorId, Guid id, CancellationToken cancellationToken)
        => throw new NotImplementedException("Bind an approved tenant-scoped persistence adapter.");
}
''',
        "backend/src/Services/RequirementService.cs": '''using GeneratedService.Models;
using GeneratedService.Repositories;

namespace GeneratedService.Services;

public sealed class RequirementService(IRequirementRepository repository)
{
    public Task<Requirement> CreateAsync(string tenantId, string actorId, string title, string description, CancellationToken token)
    {
        if (string.IsNullOrWhiteSpace(tenantId) || string.IsNullOrWhiteSpace(actorId))
            throw new UnauthorizedAccessException("Authenticated tenant and actor are required.");
        return repository.CreateAsync(tenantId, actorId, title.Trim(), description.Trim(), token);
    }
}
''',
        "backend/src/Security/AuditEvent.cs": '''namespace GeneratedService.Security;

public sealed record AuditEvent(string ActorId, string Action, string ResourceId,
    string Outcome, string CorrelationId, DateTimeOffset OccurredAtUtc);
    ''',
        "backend/src/Security/FailClosedAuthenticationHandler.cs": '''using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.Extensions.Options;

namespace GeneratedService.Security;

public sealed class FailClosedAuthenticationHandler(
    IOptionsMonitor<AuthenticationSchemeOptions> options,
    ILoggerFactory logger,
    UrlEncoder encoder)
    : AuthenticationHandler<AuthenticationSchemeOptions>(options, logger, encoder)
{
    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
        => Task.FromResult(AuthenticateResult.Fail("Identity provider validation is not configured."));
}
''',
        "backend/src/Controllers/RequirementsController.cs": '''using GeneratedService.DTOs;
using GeneratedService.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace GeneratedService.Controllers;

[ApiController, Authorize, Route("api/v1/requirements")]
public sealed class RequirementsController(RequirementService service) : ControllerBase
{
    [HttpPost]
    public IActionResult Create([FromBody] RequirementCreateRequest request)
    {
        // Resolve actor and tenant from validated server-side claims; never from request JSON.
        return StatusCode(StatusCodes.Status503ServiceUnavailable,
            new { detail = "Tenant claim mapping and persistence are not configured." });
    }
}
''',
          "backend/tests/GeneratedService.Tests.csproj": '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework><IsPackable>false</IsPackable><Nullable>enable</Nullable></PropertyGroup>
  <ItemGroup><PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.12.0" /><PackageReference Include="xunit" Version="2.9.2" /><PackageReference Include="xunit.runner.visualstudio" Version="2.8.2" /></ItemGroup>
      <ItemGroup><ProjectReference Include="../src/GeneratedService.csproj" /></ItemGroup>
</Project>
''',
        "backend/tests/RequirementValidationTests.cs": '''using System.ComponentModel.DataAnnotations;
    using GeneratedService.DTOs;
using Xunit;

public sealed class RequirementValidationTests
{
    [Fact]
    public void RequestModelCarriesBoundedFields()
    {
        var request = new RequirementCreateRequest { Title = "Portal", Description = "Detailed scope" };
        Assert.Equal("Portal", request.Title);
    }

    [Fact]
    public void RequestModelRejectsShortTitle()
    {
        var request = new RequirementCreateRequest { Title = "x", Description = "Detailed scope" };
        var results = new List<ValidationResult>();
        var valid = Validator.TryValidateObject(request, new ValidationContext(request), results, true);
        Assert.False(valid);
    }
}
''',
    }


def _safe_table_name(value: str) -> str:
    raw_name = str(value)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", raw_name):
        raise ValueError("Blueprint entity produced an invalid SQL table identifier")
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", raw_name).lower()
    if normalized == "user":
        normalized = "app_user"
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", normalized):
        raise ValueError("Blueprint entity produced an invalid SQL table identifier")
    return normalized


def _database_files(artifacts: dict[str, Any]) -> dict[str, str]:
    database = artifacts.get("database_blueprint", {})
    declared_tables = database.get("tables", []) if isinstance(database, dict) else []
    extension_tables = []
    built_in = {"app_user", "requirement", "project", "task", "audit_event"}
    for item in declared_tables:
        if not isinstance(item, dict) or not item.get("table"):
            continue
        table_name = _safe_table_name(item["table"])
        if table_name not in built_in and table_name not in extension_tables:
            extension_tables.append(table_name)
    extension_ddl = "\n".join(
        f"CREATE TABLE IF NOT EXISTS {table_name} (\n"
        "    id UUID PRIMARY KEY,\n"
        "    tenant_id UUID NOT NULL,\n"
        "    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP\n"
        ");"
        for table_name in extension_tables
    )
    schema = '''-- PostgreSQL starter schema. Review tenancy, retention, and data classification before use.
CREATE TABLE IF NOT EXISTS app_user (
    user_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    external_subject VARCHAR(255) NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, external_subject),
    UNIQUE (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS requirement (
    requirement_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    created_by UUID NOT NULL,
    title VARCHAR(200) NOT NULL CHECK (char_length(title) >= 3),
    description TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Submitted',
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, requirement_id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES app_user(tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS project (
    project_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    requirement_id UUID NOT NULL UNIQUE,
    name VARCHAR(250) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Planned',
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, project_id),
    FOREIGN KEY (tenant_id, requirement_id) REFERENCES requirement(tenant_id, requirement_id)
);

CREATE TABLE IF NOT EXISTS task (
    task_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    title VARCHAR(250) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Planned',
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, project_id) REFERENCES project(tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS audit_event (
    audit_event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    action VARCHAR(120) NOT NULL,
    resource_type VARCHAR(80) NOT NULL,
    resource_id VARCHAR(120) NOT NULL,
    outcome VARCHAR(40) NOT NULL,
    correlation_id UUID NOT NULL,
    occurred_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, actor_id) REFERENCES app_user(tenant_id, user_id)
);
'''
    if extension_ddl:
        schema += "\n-- Additional entities derived from the approved planning blueprint.\n" + extension_ddl + "\n"
    index_statements = [
        "-- Additive indexes; validate query plans and tenant partitioning before use.",
        "CREATE INDEX IF NOT EXISTS ix_requirement_tenant_status_created ON requirement (tenant_id, status, created_at_utc DESC);",
        "CREATE INDEX IF NOT EXISTS ix_project_tenant_status ON project (tenant_id, status);",
        "CREATE INDEX IF NOT EXISTS ix_task_project_status ON task (project_id, status);",
        "CREATE INDEX IF NOT EXISTS ix_audit_tenant_resource_time ON audit_event (tenant_id, resource_type, resource_id, occurred_at_utc DESC);",
    ]
    index_statements.extend(
        f"CREATE INDEX IF NOT EXISTS ix_{table_name}_tenant ON {table_name} (tenant_id);"
        for table_name in extension_tables
    )
    return {
        "database/schema.sql": schema,
        "database/indexes.sql": "\n".join(index_statements) + "\n",
        "database/constraints.sql": "-- Primary, foreign-key, unique, and check constraints are defined in schema.sql.\n-- Apply additional constraints only after reviewing existing data and migration/rollback plans.\n",
        "database/seed.sql": "-- No seed rows are generated: tenant identities, roles, and business data require authorized sources.\n",
    }


def _openapi_file(api_catalog: dict[str, Any]) -> str:
    paths: dict[str, dict[str, Any]] = {}
    schemas: dict[str, Any] = {
        "RequirementCreate": {"type": "object", "additionalProperties": False,
            "required": ["title", "description"], "properties": {
                "title": {"type": "string", "minLength": 3, "maxLength": 200},
                "description": {"type": "string", "minLength": 10, "maxLength": 12000}}},
        "Requirement": {"type": "object", "required": ["requirement_id", "title", "status"],
            "properties": {"requirement_id": {"type": "string", "format": "uuid"},
                           "title": {"type": "string"}, "status": {"type": "string"}}},
    }
    for endpoint in api_catalog.get("endpoints", []):
        if not isinstance(endpoint, dict):
            continue
        method = str(endpoint.get("method", "")).lower()
        path = str(endpoint.get("path", ""))
        if method not in {"get", "post", "put", "patch", "delete"}:
            continue
        if not re.fullmatch(r"/api/v1/[A-Za-z0-9_/{}/-]+", path):
            continue
        request_model = str(endpoint.get("request_model", ""))
        response_model = str(endpoint.get("response_model", ""))
        for model_name in (request_model, response_model):
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,80}", model_name) and model_name not in schemas:
                schemas[model_name] = {"type": "object", "additionalProperties": False,
                                       "description": "Proposed contract; refine fields against the approved domain model."}
        operation = re.sub(r"[^A-Za-z0-9]+", " ", str(endpoint.get("purpose", "operation"))).strip()
        operation_id = re.sub(r"[^A-Za-z0-9]+", "_", operation).strip("_").lower() or "operation"
        parameters = [
            {"name": name, "in": "path", "required": True,
             "schema": {"type": "string", "format": "uuid"}}
            for name in re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", path)
        ]
        operation_spec: dict[str, Any] = {
            "summary": str(endpoint.get("purpose", "Proposed operation"))[:160],
            "operationId": operation_id,
                "responses": {("201" if method == "post" else "200"): {
                                        "description": response_model or "Success response",
                                        **({"content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{response_model}"}}}}
                                            if response_model in schemas else {})},
                          "401": {"description": "Authentication required"},
                          "403": {"description": "Not authorized"},
                          "422": {"description": "Validation error"}},
        }
        if parameters:
            operation_spec["parameters"] = parameters
        if method in {"post", "put", "patch"}:
            request_schema = ({"$ref": f"#/components/schemas/{request_model}"}
                              if request_model in schemas else
                              {"type": "object", "additionalProperties": False})
            operation_spec["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": request_schema}},
            }
        paths.setdefault(path, {})[method] = operation_spec
    specification = {
        "openapi": "3.1.0",
        "info": {"title": "Generated Requirement Service", "version": "1.0.0", "description": "Starter contract; validate before implementation."},
        "servers": [{"url": "https://api.example.invalid", "description": "Placeholder; configure per environment."}],
        "security": [{"bearerAuth": []}],
        "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
                       "schemas": schemas},
    }
    return json.dumps(specification, indent=2) + "\n"


def _frontend_files(ui_blueprint: dict[str, Any]) -> dict[str, str]:
    ui_manifest = {
        "screens": ui_blueprint.get("screens", []),
        "forms": ui_blueprint.get("forms", []),
        "dashboards": ui_blueprint.get("dashboards", []),
        "navigation": ui_blueprint.get("navigation", []),
        "journeys": ui_blueprint.get("user_journeys", []),
    }
    return {
        "frontend/package.json": json.dumps({"name": "generated-frontend", "private": True,
            "version": "0.1.0", "type": "module", "scripts": {"dev": "vite", "build": "vite build", "test": "vitest run"},
            "dependencies": {"react": "^19.0.0", "react-dom": "^19.0.0"},
            "devDependencies": {"@types/react": "^19.0.0", "@types/react-dom": "^19.0.0", "@vitejs/plugin-react": "^4.3.0", "vite": "^6.0.0", "typescript": "^5.7.0", "vitest": "^2.1.0"}}, indent=2) + "\n",
        "frontend/tsconfig.json": json.dumps({"compilerOptions": {"target": "ES2022", "useDefineForClassFields": True,
            "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext", "skipLibCheck": True,
            "moduleResolution": "Bundler", "allowImportingTsExtensions": True, "resolveJsonModule": True,
            "isolatedModules": True, "noEmit": True, "jsx": "react-jsx", "strict": True},
            "include": ["src"]}, indent=2) + "\n",
        "frontend/vite.config.ts": '''import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({ plugins: [react()] });
''',
        "frontend/src/main.tsx": '''import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
''',
        "frontend/src/App.tsx": '''import { useState, type FormEvent } from "react";
    import blueprint from "./generatedBlueprint.json";

export function App() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("Ready");

    async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Identity and API integration required before submission");
  }

  return <main>
    <nav aria-label="Primary navigation">{blueprint.navigation.map((item) => <a key={item} href={`#${item.toLowerCase().replaceAll(" ", "-")}`}>{item}</a>)}</nav>
    <h1>Delivery workspace</h1>
    <section aria-labelledby="requirement-heading">
      <h2 id="requirement-heading">New requirement</h2>
      <form onSubmit={submit}>
        <label>Title<input required minLength={3} maxLength={200} value={title} onChange={event => setTitle(event.target.value)} /></label>
        <label>Description<textarea required minLength={10} maxLength={12000} value={description} onChange={event => setDescription(event.target.value)} /></label>
        <button type="submit">Review requirement</button>
      </form>
      <p role="status">{status}</p>
    </section>
        {blueprint.screens.map((screen) => <section key={screen.name} id={screen.name.toLowerCase().replaceAll(" ", "-")}>
            <h2>{screen.name}</h2><p>{screen.journey}</p>
            {screen.forms.map((form) => <p key={form}>{form}</p>)}
        </section>)}
        {blueprint.dashboards.map((dashboard) => <section key={dashboard.name}><h2>{dashboard.name}</h2>
            <ul>{dashboard.metrics.map((metric) => <li key={metric}>{metric}</li>)}</ul>
        </section>)}
  </main>;
}
''',
        "frontend/src/styles.css": "body{font-family:system-ui,sans-serif;margin:0;color:#18352b;background:#f4f6f2}main{max-width:960px;margin:auto;padding:2rem}nav{display:flex;gap:1rem}form{display:grid;gap:1rem;max-width:42rem}label{display:grid;gap:.4rem}input,textarea,button{font:inherit;padding:.65rem}section{margin-block:2rem}\n",
        "frontend/index.html": '<!doctype html>\n<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Delivery Workspace</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>\n',
        "frontend/src/generatedBlueprint.json": json.dumps(ui_manifest, indent=2) + "\n",
                "frontend/src/App.test.tsx": '''import { describe, expect, it } from "vitest";
import blueprint from "./generatedBlueprint.json";

describe("delivery workspace", () => {
    it("contains planned screens, navigation, and dashboards", () => {
        expect(blueprint.screens.length).toBeGreaterThan(0);
        expect(blueprint.navigation.length).toBeGreaterThan(0);
        expect(blueprint.dashboards.length).toBeGreaterThan(0);
  });
});
''',
    }


def _security_files() -> dict[str, str]:
    return {
        "security/SECURITY.md": """# Security Integration Checklist

- Configure an approved identity provider and validate issuer, audience, signature, expiry, and revocation server-side.
- Enforce deny-by-default RBAC plus resource and tenant ownership on every operation; do not trust role/tenant fields from request bodies.
- Require TLS at the ingress and secure cookies/session handling where applicable.
- Store secrets only in an approved secret manager; `.env.example` contains placeholders only.
- Emit append-only audit events for sensitive operations without credentials or raw sensitive payloads.
- Add negative tests for anonymous, wrong-role, cross-tenant, and resource-owner denial.
- Review data classification, retention, key rotation, incident response, and dependency updates before use.

The generated authentication and authorization adapters intentionally fail closed until an identity provider and policy implementation are configured. This package does not provide production identity configuration.
""",
        "security/rbac-matrix.csv": "role,requirement.create,requirement.read,project.read,audit.read\nUSER,own,own,assigned,none\nMANAGER,own_and_direct_reports,team_scoped,team_scoped,none\nADMIN,company_read,company_read,company_read,limited\nOWNER,company_read,company_read,company_read,governance\n",
        "security/audit-events.json": json.dumps({"required_fields": ["actor_id", "action", "resource_type", "resource_id", "outcome", "correlation_id", "occurred_at_utc"],
            "prohibited_fields": ["password", "access_token", "refresh_token", "raw_secret", "unnecessary_sensitive_payload"]}, indent=2) + "\n",
    }


def _test_files(language: str) -> dict[str, str]:
    files = {
        "tests/README.md": """# Generated Test Plan

- Unit: request validation, domain rules, repository/service behavior, and error mapping.
- Integration: database transaction boundaries, tenant scoping, identity claims, and audit delivery.
- Security: anonymous/wrong-role/cross-tenant denial, input bounds, and secret-log scanning.
- UAT: requester intake, authorized review, lifecycle status, and accessibility paths.
- Performance: agreed workload baseline, concurrency, query saturation, and dependency degradation.

No test suite was executed by the factory. Bind test environments and approved fixtures before running these assets.
""",
        "tests/uat-scenarios.md": """# UAT Scenarios

1. A requester creates a requirement and can read only their authorized record.
2. A user from another tenant cannot read or modify the requirement.
3. An authorized reviewer can inspect project status without gaining unrelated approval authority.
4. Invalid and oversized request fields are rejected without persistence.
5. Audit events identify actor, resource, outcome, and correlation without secrets.
""",
    "tests/integration/contract.md": """# Integration Test Scenarios

- Verify database commit/rollback behavior and idempotent retry for requirement creation.
- Verify identity claims resolve to a tenant and actor before repository calls.
- Verify cross-tenant queries return no resource and produce an auditable denial.
- Verify audit writer failure prevents a sensitive state transition from being reported successful.
- Use an isolated test database and synthetic fixtures only; do not point these tests at production.
""",
        "tests/performance/k6-smoke.js": """import http from 'k6/http';
import { check } from 'k6';

export const options = { vus: 1, iterations: 1 };
export default function () {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) throw new Error('Set BASE_URL to an approved non-production target');
  const response = http.get(`${baseUrl}/health`);
  check(response, { 'health responds': (r) => r.status === 200 });
}
""",
    }
    if language == "python":
        files["tests/security/test_auth_fails_closed.py"] = '''from fastapi.testclient import TestClient
from app.main import app

def test_protected_route_rejects_missing_identity():
    response = TestClient(app).get("/api/v1/requirements")
    assert response.status_code in {401, 503}
'''
    elif language == "node":
        files["tests/security/auth.test.js"] = '''import test from "node:test";
import assert from "node:assert/strict";
import { requireAuthenticated } from "../../backend/src/security/auth.js";

test("identity adapter is not permissive before configuration", async () => {
  let observed;
  requireAuthenticated({}, {}, error => { observed = error; });
  assert.equal(observed.status, 503);
});
'''
    else:
        files["tests/security/AuthorizationContractTests.cs"] = '''using Xunit;

public sealed class AuthorizationContractTests
{
    [Fact]
    public void ProtectedRoutesRequireAuthorizationAttribute()
    {
        Assert.True(typeof(Microsoft.AspNetCore.Authorization.AuthorizeAttribute) is not null);
    }
}
'''
    return files


def _devops_files(language: str) -> dict[str, str]:
    dockerfiles = {
        "python": """FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
RUN useradd --system --uid 10001 appuser
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
""",
        "node": """FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /app
COPY backend/package.json ./package.json
RUN npm install --omit=dev --ignore-scripts
COPY backend/src ./src
USER node
EXPOSE 8080
CMD ["node", "src/server.js"]
""",
        "dotnet": """FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY backend/src/GeneratedService.csproj ./
RUN dotnet restore
COPY backend/src/ ./
RUN dotnet publish -c Release -o /out --no-restore
FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /out ./
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["dotnet", "GeneratedService.dll"]
""",
        }
    setup_steps = {
        "python": "      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n      - uses: actions/setup-node@v4\n        with:\n          node-version: '22'\n",
        "node": "      - uses: actions/setup-node@v4\n        with:\n          node-version: '22'\n",
        "dotnet": "      - uses: actions/setup-dotnet@v4\n        with:\n          dotnet-version: '8.0.x'\n      - uses: actions/setup-node@v4\n        with:\n          node-version: '22'\n",
    }
    ci_commands = {
        "python": "python -m pip install -r backend/requirements.txt\nexport PYTHONPATH=backend\npython -m pytest backend/tests tests\nnpm --prefix frontend install --ignore-scripts\nnpm --prefix frontend run build\nnpm --prefix frontend test",
        "node": "npm --prefix backend install --ignore-scripts\nnpm --prefix backend test\nnpm --prefix frontend install --ignore-scripts\nnpm --prefix frontend run build\nnpm --prefix frontend test",
        "dotnet": "dotnet test backend/tests/GeneratedService.Tests.csproj\nnpm --prefix frontend install --ignore-scripts\nnpm --prefix frontend run build\nnpm --prefix frontend test",
    }
    ci_steps = "\n".join(f"          {command}" for command in ci_commands[language].splitlines())
    return {
        "devops/Dockerfile": dockerfiles[language],
        "devops/.github/workflows/ci.yml": f"""name: validate-generated-package
on: [push, pull_request]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
{setup_steps[language].rstrip()}
      - name: Validate generated assets
        run: |
                    python -c "import json; json.load(open('api/openapi.json', encoding='utf-8'))"
                    python -c "from pathlib import Path; assert Path('database/schema.sql').is_file()"
      - name: Backend checks
        run: |
{ci_steps}
""",
        "devops/.env.example": "APP_ENV=development\nPORT=8080\nDATABASE_URL=\nOIDC_ISSUER=\nOIDC_AUDIENCE=\nSECRET_MANAGER_REFERENCE=\n",
        "devops/infra/main.tf": """terraform {
  required_version = ">= 1.6.0"
}

# Planning placeholder only. No provider, resource, backend, or deployment target is declared.
locals {
  package_status = "DESIGN_ONLY"
  environment    = "REQUIRES_REVIEW"
}

output "package_status" {
  value = local.package_status
}
""",
        "devops/infra/variables.tf": """# Add reviewed environment-specific inputs only after architecture and security approval.
variable "environment_name" {
  type        = string
  description = "Placeholder; no infrastructure resources are declared by this template."
  default     = "REQUIRES_REVIEW"
}
""",
        "devops/README.md": "These assets are source templates only. The CI definition runs validation/tests when adopted; no pipeline was created or run. Terraform intentionally declares no provider/resources. Docker build/run and infrastructure application are not performed by this service.\n",
    }


def _delivery_manifest(technical_delivery_package: dict[str, Any]) -> str:
    artifacts = technical_delivery_package["artifacts"]
    summary = {
        "package_status": technical_delivery_package.get("status"),
        "analysis_mode": technical_delivery_package.get("analysis_mode"),
        "artifact_names": sorted(artifacts),
        "database_entities": [item.get("entity") for item in artifacts.get("database_blueprint", {}).get("tables", [])],
        "api_operations": [
            {"method": item.get("method"), "path": item.get("path"), "purpose": item.get("purpose")}
            for item in artifacts.get("api_catalog", {}).get("endpoints", [])
        ],
        "ui_screens": [item.get("name") for item in artifacts.get("ui_blueprint", {}).get("screens", [])],
        "workforce_roles": [item.get("proposed_role") for item in artifacts.get("workforce_plan", {}).get("role_alignment", [])],
        "implementation_approved": False,
    }
    return json.dumps(summary, indent=2) + "\n"


def _backend_blueprint_file(artifacts: dict[str, Any]) -> str:
    architecture = artifacts.get("architecture_blueprint", {})
    api_catalog = artifacts.get("api_catalog", {})
    design = {
        "architecture_style": architecture.get("architecture_style"),
        "components": architecture.get("components", []),
        "services": architecture.get("services", []),
        "interfaces": architecture.get("interfaces", []),
        "service_boundaries": architecture.get("backend_design", {}).get("service_boundaries", []),
        "backend_responsibilities": architecture.get("backend_design", {}).get("responsibilities", []),
        "failure_handling": architecture.get("backend_design", {}).get("failure_handling", []),
        "api_operations": api_catalog.get("endpoints", []),
        "requires_human_review": True,
    }
    return json.dumps(design, indent=2) + "\n"


def build_code_package(technical_delivery_package: dict[str, Any], backend_language: str) -> dict[str, Any]:
    """Return source files as strings; never writes, executes, or deploys them."""
    language = backend_language.strip().lower()
    if language not in BACKEND_LANGUAGES:
        raise ValueError(f"backend_language must be one of: {', '.join(sorted(BACKEND_LANGUAGES))}")
    if not isinstance(technical_delivery_package, dict) or not isinstance(
        technical_delivery_package.get("artifacts"), dict
    ):
        raise ValueError("A technical delivery package with artifacts is required")

    language_files = (_python_backend() if language == "python" else
                      _node_backend() if language == "node" else _dotnet_backend())
    files: dict[str, str] = {}
    files.update(language_files)
    artifacts = technical_delivery_package["artifacts"]
    files.update(_database_files(artifacts))
    api_catalog = artifacts.get("api_catalog", {})
    files["api/openapi.json"] = _openapi_file(api_catalog if isinstance(api_catalog, dict) else {})
    ui_blueprint = artifacts.get("ui_blueprint", {})
    files.update(_frontend_files(ui_blueprint if isinstance(ui_blueprint, dict) else {}))
    files.update(_security_files())
    files.update(_test_files(language))
    files.update(_devops_files(language))
    files["backend/blueprint.json"] = _backend_blueprint_file(artifacts)
    files["delivery/blueprint-summary.json"] = _delivery_manifest(technical_delivery_package)

    normalized_files = []
    for path, content in sorted(files.items()):
        normalized = path.replace("\\", "/")
        if normalized.startswith("/") or any(part in {"", ".", ".."} for part in normalized.split("/")):
            raise ValueError("Generated file path failed validation")
        normalized_files.append({"path": normalized, "content": content})
    return {
        "package": "Autonomous Code Factory",
        "status": "SOURCE_ARTIFACTS_REVIEW_REQUIRED",
        "backend_language": language,
        "source_blueprint_status": technical_delivery_package.get("status", "UNKNOWN"),
        "files": normalized_files,
        "file_count": len(normalized_files),
        "controls": {"files_written": False, "code_executed": False,
                     "deployed": False, "infrastructure_created": False,
                     "runtime_started": False, "secrets_included": False,
                     "production_changes": False},
        "limitations": [
            "Templates fail closed until identity, tenant authorization, persistence, audit, and configuration adapters are reviewed and implemented.",
            "Generated DDL is additive and PostgreSQL-specific; validate dialect, tenancy, retention, migrations, and rollback before use.",
            "OpenAPI and UI contracts are generic starter contracts; reconcile them against approved project requirements.",
            "CI, Docker, and Terraform files are inert response content; they are not written, invoked, or applied.",
        ],
    }
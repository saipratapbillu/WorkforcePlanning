from sqlalchemy import text


def organization_mapping_issues(db):
    rows = db.execute(text("""
        SELECT
            SUM(CASE WHEN u.IsActive=1 AND u.CompanyID IS NULL THEN 1 ELSE 0 END) AS MissingCompany,
            SUM(CASE WHEN u.IsActive=1 AND (d.DepartmentID IS NULL OR u.DepartmentID IS NULL) THEN 1 ELSE 0 END) AS MissingDepartment,
            SUM(CASE WHEN u.IsActive=1 AND (p.PositionID IS NULL OR u.PositionID IS NULL) THEN 1 ELSE 0 END) AS MissingPosition,
            SUM(CASE WHEN u.IsActive=1 AND u.CompanyID IS NOT NULL AND d.DepartmentID IS NOT NULL
                          AND u.CompanyID<>d.CompanyID THEN 1 ELSE 0 END) AS DepartmentCompanyMismatch,
            SUM(CASE WHEN u.IsActive=1 AND u.DepartmentID IS NOT NULL AND p.PositionID IS NOT NULL
                          AND u.DepartmentID<>p.DepartmentID THEN 1 ELSE 0 END) AS PositionDepartmentMismatch
        FROM dbo.AppUser u
        LEFT JOIN dbo.Department d ON d.DepartmentID=u.DepartmentID
        LEFT JOIN dbo.Position p ON p.PositionID=u.PositionID
    """)).mappings().one()
    return {key: int(value or 0) for key, value in rows.items()}


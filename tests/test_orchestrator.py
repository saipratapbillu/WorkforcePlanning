from app.services.orchestrator import classify_requirement

def test_supplier_routing():
    x=classify_requirement('Build supplier compliance with SharePoint SQL Server and Power BI')
    assert 'Procurement' in x['departments']
    assert 'Data & Analytics' in x['departments']
    assert 'Cybersecurity' in x['departments']

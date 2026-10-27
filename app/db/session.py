import os
from dotenv import load_dotenv
from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
load_dotenv()
DATABASE_URL=os.getenv("DATABASE_URL", "mssql+pyodbc://@localhost/AICompany?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes")
engine=create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal=sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
class Base(DeclarativeBase): pass
def get_db(request: Request):
    db=SessionLocal()
    try:
        principal = getattr(request.state, "security_principal", None)
        if principal:
            db.execute(text("EXEC sys.sp_set_session_context @key=N'UserID', @value=:user_id"), {
                "user_id": principal["sub"],
            })
        yield db
    finally:
        try:
            db.rollback()
            db.execute(text("EXEC sys.sp_set_session_context @key=N'UserID', @value=NULL"))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

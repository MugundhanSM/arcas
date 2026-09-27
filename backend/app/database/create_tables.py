from app.database.models import Base
from app.database.session import engine

Base.metadata.create_all(bind=engine)

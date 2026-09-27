from sqlalchemy.orm import Session

from app.database.models import User


class UserRepository:

    @staticmethod
    def create(db: Session, username: str, hashed_password: str) -> User:
        user = User(
            username=username,
            hashed_password=hashed_password,
            is_active=1,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def find_by_username(db: Session, username: str):
        return (
            db.query(User)
            .filter(User.username == username)
            .first()
        )

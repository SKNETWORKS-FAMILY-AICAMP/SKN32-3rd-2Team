from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..models import User

MAX_PAGE_SIZE = 100


def get_user_list_by_params(
    db: Session,
    name: str | None = None,
    department: str | None = None,
    is_disabled: bool | None = None,
    is_admin: bool | None = None,
    page: int = 1,
    size: int = 20,
):
    """조건에 맞는 유저 목록을 페이지 단위로 조회한다.
    admin/users.py의 페이지 라우트와 API 라우트가 이 함수를 공유한다."""

    page = max(page, 1)
    size = min(max(size, 1), MAX_PAGE_SIZE)

    stmt = select(User)

    if name:
        stmt = stmt.where(User.name.like(f"%{name}%"))

    if department:
        stmt = stmt.where(User.department == department)

    if is_disabled is not None:
        stmt = stmt.where(User.is_disabled == is_disabled)

    if is_admin is not None:
        stmt = stmt.where(User.is_admin == is_admin)

    # 전체 개수 조회
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    # 최신 가입자 순
    stmt = (
        stmt
        .order_by(desc(User.created_at))
        .offset((page - 1) * size)
        .limit(size)
    )

    users = db.scalars(stmt).all()

    return {
        "items": [
            {
                "id": user.user_id,
                "name": user.name,
                "department": user.department,
                "is_disabled": user.is_disabled,
                "is_admin": user.is_admin,
                "created_at": user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else "",
            }
            for user in users
        ],
        "page": page,
        "size": size,
        "total": total,
        "total_pages": (total + size - 1) // size if total else 1,
    }
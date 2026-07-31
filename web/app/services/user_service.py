import re

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..models import User, UserLoginHistory

MAX_PAGE_SIZE = 100
USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{4,20}$")

def record_login(db: Session, user_id: str) -> None:
    """로그인 성공 시 user_login_history에 이력 한 건을 남긴다."""
    db.add(UserLoginHistory(user_id=user_id))
    db.commit()

class UserServiceError(Exception):
    """유저 생성/수정 중 발생하는 검증 오류. 라우터에서 status_code로 매핑해서 응답한다."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_user_by_admin(
    db: Session,
    user_id: str,
    passwd: str,
    passwd_confirm: str,
    name: str,
    department: str,
    is_admin: bool | None = None,
    is_disabled: bool | None = None,
) -> User:
    """관리자가 '유저 추가' 모달에서 신규 계정을 생성한다. (회원가입과 동일한 검증 규칙)"""

    if not USER_ID_PATTERN.match(user_id):
        raise UserServiceError("아이디는 영문/숫자 4~20자로 입력해주세요.")

    if len(passwd) < 8:
        raise UserServiceError("비밀번호는 8자 이상이어야 합니다.")

    if passwd != passwd_confirm:
        raise UserServiceError("비밀번호가 일치하지 않습니다.")

    if db.get(User, user_id) is not None:
        raise UserServiceError("이미 사용 중인 아이디입니다.", status_code=409)

    new_user = User(
        user_id=user_id,
        passwd=hash_password(passwd),
        name=name,
        department=department,
        is_admin=True if is_admin is not None else False,
        is_disabled=True if is_disabled is not None else False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def update_user_profile(
    db: Session,
    user_id: str,
    name: str | None = None,
    department: str | None = None,
    passwd: str | None = None,
    is_admin: bool | None = None,
    is_disabled: bool | None = None,
) -> User:
    """유저관리 화면의 수정 모달: 이름 / 부서명 / 비밀번호 / 관리자권한 / 비활성여부를 수정한다.
    (user_id는 이 경로로 변경할 수 없다)"""

    user = db.get(User, user_id)
    if user is None:
        raise UserServiceError("사용자를 찾을 수 없습니다.", status_code=404)

    if name:
        user.name = name

    if department:
        user.department = department

    if passwd:
        if len(passwd) < 8:
            raise UserServiceError("비밀번호는 8자 이상이어야 합니다.")
        user.passwd = hash_password(passwd)

    if is_admin is not None:
        user.is_admin = is_admin

    if is_disabled is not None:
        user.is_disabled = is_disabled

    db.commit()
    db.refresh(user)
    return user


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
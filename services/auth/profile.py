"""Owner-only profile data; identity name and metadata are saved atomically."""
import base64
import binascii
from io import BytesIO
import re
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Principal
from .passwords import hash_password, validate_password, verify_password
from .service import AuthService
from .store import AccountConflict


class ProfileFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(default="", max_length=254)
    grade: Literal["", "七年级", "八年级", "九年级"] = ""
    bio: str = Field(default="", max_length=300)
    avatar_data_url: str = Field(default="", max_length=1_400_000)
    reading_size: Literal["standard", "large"] = "standard"

    @field_validator("email")
    @classmethod
    def email_format(cls, value: str) -> str:
        if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("邮箱格式不正确")
        return value


class ProfileUpdate(ProfileFields):
    display_name: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=0)
    expected_user_id: str | None = None


class StoredProfile(ProfileFields):
    revision: int = Field(default=0, ge=0)


class ProfileView(StoredProfile):
    user_id: str
    username: str
    display_name: str


def avatar_image(value: str) -> str:
    if not value:
        return ""
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", value)
    if not match:
        raise ValueError("头像仅支持 PNG、JPEG 或 WebP 图片")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
        if len(raw) > 1024 * 1024:
            raise ValueError("头像文件不能超过 1 MB")
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"} or source.width * source.height > 16_000_000:
                raise ValueError("图片格式或尺寸不支持")
            source.load()
            picture = source.convert("RGB")
            picture.thumbnail((256, 256))
            output = BytesIO()
            picture.save(output, format="WEBP", quality=82)
        return "data:image/webp;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except (UnidentifiedImageError, OSError, binascii.Error, Image.DecompressionBombError) as exc:
        raise ValueError("头像文件损坏或不是有效图片") from exc


def read_profile(identity: AuthService, principal: Principal) -> ProfileView:
    identity._require_accounts_mode()
    user, raw = identity.store.get_profile(principal.user_id)
    profile = StoredProfile.model_validate(raw)
    return ProfileView(**profile.model_dump(), user_id=user.user_id,
                       username=user.username, display_name=user.display_name)


def save_profile(identity: AuthService, principal: Principal, payload: ProfileUpdate, request_id: str) -> ProfileView:
    identity._require_accounts_mode()
    if payload.expected_user_id is not None and payload.expected_user_id != principal.user_id:
        raise AccountConflict("当前登录账号已切换，请重新载入资料。")
    current = read_profile(identity, principal)
    data = payload.model_dump(exclude={"display_name", "expected_revision", "expected_user_id"})
    if payload.avatar_data_url != current.avatar_data_url:
        data["avatar_data_url"] = avatar_image(payload.avatar_data_url)
    identity.store.update_user(
        principal.user_id, display_name=payload.display_name,
        profile_data=data, expected_profile_revision=payload.expected_revision,
        expected_auth_version=principal.auth_version,
        audit=identity._admin_change_audit(actor=principal, action="profile.update",
            resource_id=principal.user_id, request_id=request_id, details={"revision": payload.expected_revision + 1}),
    )
    return read_profile(identity, principal)


def change_password(identity: AuthService, principal: Principal, current_password: str,
                    new_password: str, request_id: str) -> None:
    identity._require_accounts_mode()
    user = identity.store.get_user(principal.user_id)
    if user is None or not verify_password(current_password, user.password_hash):
        raise ValueError("当前密码不正确")
    try:
        validate_password(new_password)
    except ValueError as exc:
        raise ValueError("新密码至少需要 12 个字符，编码长度不能超过 256 字节。") from exc
    if verify_password(new_password, user.password_hash):
        raise ValueError("新密码不能与当前密码相同")
    identity.store.update_user(
        principal.user_id, password_hash=hash_password(new_password),
        expected_auth_version=principal.auth_version, expected_password_hash=user.password_hash,
        audit=identity._admin_change_audit(actor=principal, action="profile.password_change",
            resource_id=principal.user_id, request_id=request_id, details={}),
    )

"""跨 view 共用的權限與範圍輔助函式。"""
from ..models import Device, UserProfile


def get_profile(user):
    """Return UserProfile, creating a default one if missing.
    Django superuser 自動對應到 admin 角色。
    """
    default_role = "admin" if user.is_superuser else "company_manager"
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": default_role})
    # 若已存在但 superuser 尚未設為 admin，自動修正
    if user.is_superuser and not profile.is_admin:
        profile.role = "admin"
        profile.save(update_fields=["role"])
    return profile


def get_visible_devices(user):
    """Return Device queryset scoped to the user's permission."""
    profile = get_profile(user)
    if profile.is_admin:
        return Device.objects.select_related("company").all()
    if profile.company:
        return Device.objects.select_related("company").filter(company=profile.company)
    return Device.objects.none()


def can_access_device(user, device):
    """Check whether user may access a specific device."""
    profile = get_profile(user)
    if profile.is_admin:
        return True
    return profile.company is not None and device.company_id == profile.company_id

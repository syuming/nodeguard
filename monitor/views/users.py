"""使用者管理（僅系統管理者）。"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import AdminSetPasswordForm, UserCreateForm, UserProfileForm, UserProfileMetaForm
from ..models import UserProfile
from ..utils import send_email_with_config
from .helpers import get_profile


@login_required
def user_list(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    users = User.objects.select_related("profile", "profile__company").exclude(pk=request.user.pk).order_by("username")
    return render(request, "monitor/user_list.html", {"users": users, "profile": profile})


@login_required
def user_add(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    form = UserCreateForm(request.POST or None)
    if form.is_valid():
        d = form.cleaned_data
        user = User.objects.create_user(
            username=d["username"],
            password=d["password1"],
            first_name=d["first_name"],
            last_name=d["last_name"],
            email=d["email"],
        )
        UserProfile.objects.update_or_create(user=user, defaults={"role": d["role"], "company": d["company"]})

        if "send_email" in request.POST and d["email"]:
            company_name = d["company"].name if d["company"] else "（未指定）"
            try:
                send_email_with_config(
                    subject="【NodeGuard】您的帳號已建立",
                    body=(
                        f"您好，\n\n"
                        f"您的 NodeGuard 帳號已建立，以下是登入資訊：\n\n"
                        f"  帳號：{d['username']}\n"
                        f"  密碼：{d['password1']}\n"
                        f"  所屬公司：{company_name}\n\n"
                        f"請登入後盡快修改密碼。\n\n"
                        f"系統管理者"
                    ),
                    to_list=[d["email"]],
                )
                messages.success(request, f"使用者 {user.username} 已新增，帳號密碼已寄送至 {d['email']}")
            except Exception as e:
                messages.warning(request, f"使用者 {user.username} 已新增，但 Email 寄送失敗：{e}")
        else:
            messages.success(request, f"使用者 {user.username} 已新增")

        return redirect("/users/")
    return render(request, "monitor/user_add.html", {"form": form, "profile": profile})


@login_required
def user_edit(request, pk):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    target = get_object_or_404(User.objects.select_related("profile", "profile__company"), pk=pk)
    target_profile = target.profile

    info_form = UserProfileForm(request.POST if "save_info" in request.POST else None, instance=target)
    meta_initial = {"role": target_profile.role, "company": target_profile.company}
    meta_form = UserProfileMetaForm(request.POST if "save_info" in request.POST else None, initial=meta_initial)
    pw_form = AdminSetPasswordForm(request.POST if "save_password" in request.POST else None)

    if "save_info" in request.POST and info_form.is_valid() and meta_form.is_valid():
        info_form.save()
        target_profile.role    = meta_form.cleaned_data["role"]
        target_profile.company = meta_form.cleaned_data["company"]
        target_profile.save(update_fields=["role", "company"])
        messages.success(request, f"{target.username} 的資料已更新")
        return redirect(f"/users/{pk}/edit/")

    if "save_password" in request.POST and pw_form.is_valid():
        target.set_password(pw_form.cleaned_data["new_password1"])
        target.save()
        messages.success(request, f"{target.username} 的密碼已更新")
        return redirect(f"/users/{pk}/edit/")

    return render(request, "monitor/user_edit.html", {
        "target": target, "info_form": info_form, "meta_form": meta_form,
        "pw_form": pw_form, "profile": profile
    })

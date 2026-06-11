"""登入、登出、個人資料與密碼變更。"""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render

from ..forms import UserProfileForm
from .helpers import get_profile


def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get("next", "/"))
        messages.error(request, "帳號或密碼錯誤")
    return render(request, "monitor/login.html")


def logout_view(request):
    logout(request)
    return redirect("/login/")


@login_required
def profile_edit(request):
    profile = get_profile(request.user)
    form = UserProfileForm(request.POST or None, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "個人資料已更新")
        return redirect("/profile/")
    return render(request, "monitor/profile_edit.html", {"form": form, "profile": profile})


@login_required
def change_password(request):
    profile = get_profile(request.user)
    form = PasswordChangeForm(request.user, request.POST or None)
    if form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        messages.success(request, "密碼已成功更新")
        return redirect("/")
    return render(request, "monitor/change_password.html", {"form": form, "profile": profile})

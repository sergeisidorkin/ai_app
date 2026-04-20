import io

from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from PIL import Image

from users_app.models import Employee

AVATAR_MAX_SIZE = 512
AVATAR_JPEG_QUALITY = 85


def _process_avatar(uploaded_file):
    """Resize to AVATAR_MAX_SIZE, convert to progressive JPEG, strip EXIF."""
    img = Image.open(uploaded_file)
    img = img.convert("RGB")

    if hasattr(img, "_getexif"):
        from PIL import ExifTags
        try:
            exif = img._getexif() or {}
            orientation_key = next(
                (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
            )
            orientation = exif.get(orientation_key)
            rotations = {3: 180, 6: 270, 8: 90}
            if orientation in rotations:
                img = img.rotate(rotations[orientation], expand=True)
        except Exception:
            pass

    img.thumbnail((AVATAR_MAX_SIZE, AVATAR_MAX_SIZE), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=AVATAR_JPEG_QUALITY, progressive=True, optimize=True)
    buf.seek(0)

    return InMemoryUploadedFile(
        file=buf,
        field_name="avatar",
        name="avatar.jpg",
        content_type="image/jpeg",
        size=buf.getbuffer().nbytes,
        charset=None,
    )


@login_required
def profile_view(request):
    employee = Employee.objects.filter(user=request.user).first()
    return render(request, "userprofile_app/profile.html", {"employee": employee})


@login_required
@require_POST
def profile_edit(request):
    user = request.user
    employee, _ = Employee.objects.get_or_create(user=user)

    user.first_name = request.POST.get("first_name", user.first_name)
    user.last_name = request.POST.get("last_name", user.last_name)
    user.save(update_fields=["first_name", "last_name"])

    employee.patronymic = request.POST.get("patronymic", employee.patronymic)
    if not user.is_staff:
        employee.organization = request.POST.get("organization", employee.organization)
    employee.job_title = request.POST.get("job_title", employee.job_title)

    if "password" in request.POST and request.POST["password"].strip():
        user.set_password(request.POST["password"])
        user.save(update_fields=["password"])

    employee.save()
    return redirect("user_profile")


@login_required
@require_POST
def avatar_upload(request):
    if "avatar" in request.FILES:
        employee, _ = Employee.objects.get_or_create(user=request.user)
        if employee.avatar:
            employee.avatar.delete(save=False)
        employee.avatar = _process_avatar(request.FILES["avatar"])
        employee.save(update_fields=["avatar"])
    return redirect("user_profile")


@login_required
@require_POST
def avatar_delete(request):
    employee = Employee.objects.filter(user=request.user).first()
    if employee and employee.avatar:
        employee.avatar.delete(save=False)
        employee.avatar = ""
        employee.save(update_fields=["avatar"])
    return redirect("user_profile")


@login_required
@require_POST
def profile_delete(request):
    user = request.user
    logout(request)
    user.delete()
    return redirect("login")

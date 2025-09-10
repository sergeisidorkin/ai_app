from django.shortcuts import render
from django.contrib.auth.decorators import login_required

def home_entry(request):
    """
    Точка входа:
    - анонимному пользователю показываем форму входа (Bootstrap Sign-in),
    - аутентифицированному — основную страницу (index.html).
    """
    if not request.user.is_authenticated:
        return render(request, "core/signin.html", {})
    return render(request, "index.html", {})
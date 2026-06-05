from django.shortcuts import render


def login_page(request):
    return render(request, 'portal/login.html')


def register_page(request):
    return render(request, 'portal/register.html')


def dashboard(request):
    return render(request, 'portal/dashboard.html')


def shops_page(request):
    return render(request, 'portal/shops.html')


def users_page(request):
    return render(request, 'portal/users.html')

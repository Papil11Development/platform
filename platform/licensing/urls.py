from django.urls import path

from licensing.views import StripeWebhook

urlpatterns = [
    path('stripe/', StripeWebhook.as_view())
]

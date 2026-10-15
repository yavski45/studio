from django.contrib import admin

from .models import CreditEntry, CreditPurchase, CreditReservation, CreditWallet, PaymentWebhook


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CreditWallet)
class WalletAdmin(ReadOnlyAdmin):
    list_display = ['user', 'balance_credits', 'reserved_credits', 'available_credits', 'frozen']
    search_fields = ['user__email']


@admin.register(CreditEntry)
class EntryAdmin(ReadOnlyAdmin):
    list_display = ['wallet', 'kind', 'amount', 'reference', 'created_at']
    list_filter = ['kind']


@admin.register(CreditPurchase)
class PurchaseAdmin(ReadOnlyAdmin):
    list_display = ['id', 'wallet', 'quantity', 'status', 'error_code', 'environment', 'currency', 'payment_amount', 'created_at']
    list_filter = ['status', 'environment']


@admin.register(CreditReservation)
class ReservationAdmin(ReadOnlyAdmin):
    list_display = ['job', 'wallet', 'reserved_credits', 'consumed_credits', 'status']


@admin.register(PaymentWebhook)
class WebhookAdmin(ReadOnlyAdmin):
    list_display = ['id', 'purchase', 'event', 'environment', 'status', 'attempts', 'error_code', 'received_at']
    list_filter = ['status', 'environment', 'event']

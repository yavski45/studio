from django.db import models


class DailyVisit(models.Model):
    day = models.DateField(db_index=True)
    visitor_hash = models.CharField(max_length=64)
    page_views = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['day', 'visitor_hash'], name='unique_daily_visitor')]


class MurfCreditStatus(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    key_fingerprint = models.CharField(max_length=64, blank=True)
    credits_remaining = models.PositiveBigIntegerField(null=True, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=30, blank=True)
    refresh_lease_until = models.DateTimeField(null=True, blank=True)
    threshold = models.PositiveIntegerField(default=20)

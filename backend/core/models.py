from django.conf import settings
from django.db import models


class Holding(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ticker = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    average_cost = models.DecimalField(max_digits=20, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id}:{self.ticker}"


class ForecastRun(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    horizon_days = models.IntegerField()
    baseline_mae = models.FloatField()
    improved_mae = models.FloatField()
    baseline_rmse = models.FloatField()
    improved_rmse = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id}:h{self.horizon_days}"


class AuditEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=100)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id}:{self.event_type}"


class KnowledgeSnippet(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class PriceSnapshot(models.Model):
    ticker = models.CharField(max_length=20)
    price = models.DecimalField(max_digits=20, decimal_places=6)
    as_of = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.ticker} {self.price}"

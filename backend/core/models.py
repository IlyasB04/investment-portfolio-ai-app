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


class PortfolioAccount(models.Model):
    """Virtual cash account for paper trading. One per user, created on demand."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolio_account",
    )
    cash_balance = models.DecimalField(
        max_digits=20, decimal_places=2, default=100_000
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id}: ${self.cash_balance}"


class Order(models.Model):
    class Side(models.TextChoices):
        BUY = "BUY", "Buy"
        SELL = "SELL", "Sell"

    class Status(models.TextChoices):
        FILLED = "FILLED", "Filled"
        REJECTED = "REJECTED", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ticker = models.CharField(max_length=20)
    side = models.CharField(max_length=4, choices=Side.choices)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    executed_price = models.DecimalField(max_digits=20, decimal_places=6)
    total_value = models.DecimalField(max_digits=20, decimal_places=2)
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.FILLED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} {self.side} {self.quantity} {self.ticker} @ {self.executed_price}"


class Transaction(models.Model):
    """Records the cash flow from each filled order."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="transaction")
    ticker = models.CharField(max_length=20)
    side = models.CharField(max_length=4, choices=Order.Side.choices)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    price = models.DecimalField(max_digits=20, decimal_places=6)
    total_value = models.DecimalField(max_digits=20, decimal_places=2)
    cash_after = models.DecimalField(max_digits=20, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} {self.side} {self.ticker} ${self.total_value}"


class ChatSession(models.Model):
    """
    One conversation thread between a user and the RAG assistant.
    A new session is created automatically when no session_id is supplied.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Session {self.pk} / user {self.user_id}"


class ChatMessage(models.Model):
    """Single turn in a ChatSession — either the user question or the assistant reply."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"[{self.role}] session={self.session_id} len={len(self.content)}"


class MarketPrice(models.Model):
    """
    Current simulated market price for one symbol.

    The background GBM simulator writes here every TICK_INTERVAL seconds so
    prices survive server restarts.  The in-memory cache in simulator.py is
    always the authoritative fast-path source; this table is the persistence
    layer and the cold-start seed loader.
    """

    symbol = models.CharField(max_length=20, unique=True, db_index=True)
    price = models.DecimalField(max_digits=20, decimal_places=6)
    # open_price captures the price when this symbol was first seeded so the
    # portfolio history view can show a meaningful day-start reference.
    open_price = models.DecimalField(max_digits=20, decimal_places=6)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol"]

    def __str__(self) -> str:
        return f"{self.symbol} ${self.price}"

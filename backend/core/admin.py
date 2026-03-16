from django.contrib import admin
from .models import (
    AuditEvent, ForecastRun, Holding, KnowledgeSnippet,
    Order, PortfolioAccount, PriceSnapshot, Transaction,
)

admin.site.register(Holding)
admin.site.register(ForecastRun)
admin.site.register(AuditEvent)
admin.site.register(KnowledgeSnippet)
admin.site.register(PriceSnapshot)
admin.site.register(PortfolioAccount)
admin.site.register(Order)
admin.site.register(Transaction)
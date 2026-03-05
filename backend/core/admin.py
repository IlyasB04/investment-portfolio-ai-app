from django.contrib import admin
from .models import Holding, ForecastRun, AuditEvent, KnowledgeSnippet

admin.site.register(Holding)
admin.site.register(ForecastRun)
admin.site.register(AuditEvent)
admin.site.register(KnowledgeSnippet)
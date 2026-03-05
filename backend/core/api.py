from rest_framework.viewsets import ModelViewSet
from .models import AuditEvent, Holding
from .serializers import HoldingSerializer


class HoldingViewSet(ModelViewSet):
    serializer_class = HoldingSerializer

    def get_queryset(self):
        return Holding.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        holding = serializer.save(user=self.request.user)
        AuditEvent.objects.create(
            user=self.request.user,
            event_type="holding_created",
            description=f"Created holding {holding.ticker} qty={holding.quantity} avg_cost={holding.average_cost}",
        )

    def perform_update(self, serializer):
        holding = serializer.save()
        AuditEvent.objects.create(
            user=self.request.user,
            event_type="holding_updated",
            description=f"Updated holding {holding.ticker} qty={holding.quantity} avg_cost={holding.average_cost}",
        )

    def destroy(self, request, *args, **kwargs):
        holding = self.get_object()
        AuditEvent.objects.create(
            user=request.user,
            event_type="holding_deleted",
            description=f"Deleted holding {holding.ticker} qty={holding.quantity} avg_cost={holding.average_cost}",
        )
        return super().destroy(request, *args, **kwargs)

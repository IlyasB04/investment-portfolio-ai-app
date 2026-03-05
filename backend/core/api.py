from rest_framework.viewsets import ModelViewSet
from .models import Holding
from .serializers import HoldingSerializer


class HoldingViewSet(ModelViewSet):
    serializer_class = HoldingSerializer

    def get_queryset(self):
        return Holding.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

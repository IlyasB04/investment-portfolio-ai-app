from rest_framework import serializers
from .models import Holding


class HoldingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Holding
        fields = ["id", "ticker", "quantity", "average_cost", "created_at", "updated_at"]

    def validate_ticker(self, value):
        return value.strip().upper()

"""
CSV portfolio import.

Accepts a CSV file with columns: ticker, quantity, average_cost.
Merges imported rows with existing holdings using weighted average cost.
"""

import csv
import io
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from rest_framework.decorators import api_view

from .models import AuditEvent, Holding

REQUIRED_COLUMNS = {"ticker", "quantity", "average_cost"}


def _parse_decimal(value: str) -> Decimal:
    cleaned = value.strip().replace(",", "").replace("$", "")
    return Decimal(cleaned)


@api_view(["POST"])
def import_csv(request):
    """
    POST /api/portfolio/import/

    Multipart form with field name 'file'.
    Returns { imported, merged, errors, holdings }.
    """
    file_obj = request.FILES.get("file")
    if not file_obj:
        return JsonResponse({"error": "No file uploaded. Use field name 'file'."}, status=400)

    if not file_obj.name.endswith(".csv"):
        return JsonResponse({"error": "File must be a .csv"}, status=400)

    try:
        content = file_obj.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return JsonResponse({"error": "File encoding must be UTF-8."}, status=400)

    reader = csv.DictReader(io.StringIO(content))

    # Normalise column names
    if reader.fieldnames is None:
        return JsonResponse({"error": "CSV file is empty or has no header row."}, status=400)

    columns = {c.strip().lower() for c in reader.fieldnames}
    missing = REQUIRED_COLUMNS - columns
    if missing:
        return JsonResponse(
            {"error": f"Missing required columns: {', '.join(sorted(missing))}. Required: ticker, quantity, average_cost."},
            status=400,
        )

    rows = []
    row_errors = []

    for i, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        norm = {k.strip().lower(): v for k, v in row.items()}
        ticker = norm.get("ticker", "").strip().upper()
        if not ticker:
            row_errors.append(f"Row {i}: ticker is empty.")
            continue
        try:
            quantity = _parse_decimal(norm.get("quantity", ""))
            avg_cost = _parse_decimal(norm.get("average_cost", ""))
        except InvalidOperation:
            row_errors.append(f"Row {i}: quantity and average_cost must be numbers.")
            continue
        if quantity <= 0:
            row_errors.append(f"Row {i}: quantity must be positive.")
            continue
        if avg_cost <= 0:
            row_errors.append(f"Row {i}: average_cost must be positive.")
            continue
        rows.append({"ticker": ticker, "quantity": quantity, "average_cost": avg_cost})

    if not rows and row_errors:
        return JsonResponse({"error": "No valid rows found.", "row_errors": row_errors}, status=400)

    imported_count = 0
    merged_count = 0

    for r in rows:
        existing = Holding.objects.filter(
            user=request.user, ticker__iexact=r["ticker"]
        ).first()

        if existing:
            new_qty = existing.quantity + r["quantity"]
            new_avg = (
                existing.quantity * existing.average_cost
                + r["quantity"] * r["average_cost"]
            ) / new_qty
            existing.quantity = new_qty
            existing.average_cost = new_avg
            existing.save()
            merged_count += 1
        else:
            Holding.objects.create(
                user=request.user,
                ticker=r["ticker"],
                quantity=r["quantity"],
                average_cost=r["average_cost"],
            )
            imported_count += 1

    AuditEvent.objects.create(
        user=request.user,
        event_type="csv_import",
        description=f"CSV import: {imported_count} new, {merged_count} merged. Rows with errors: {len(row_errors)}.",
    )

    holdings = Holding.objects.filter(user=request.user).order_by("ticker")
    return JsonResponse({
        "imported": imported_count,
        "merged": merged_count,
        "row_errors": row_errors,
        "total_holdings": holdings.count(),
    }, status=200)

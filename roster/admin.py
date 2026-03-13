from django.contrib import admin

from .models import Contract, Player


class ContractInline(admin.StackedInline):
    model = Contract
    extra = 0


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['name', 'position', 'jersey_number', 'years_to_retirement', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['name', 'position']
    inlines = [ContractInline]


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['player', 'total_value', 'guaranteed_ratio', 'years', 'net_worth']
    list_filter = ['years']

from decimal import Decimal

from django import forms

from .models import Contract, Player


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['name', 'position', 'jersey_number', 'years_to_retirement', 'status']
        labels = {
            'name': '이름',
            'position': '포지션',
            'jersey_number': '등번호',
            'years_to_retirement': '은퇴까지 남은 연수',
            'status': '상태',
        }


class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ['total_value', 'guaranteed_ratio', 'years', 'start_year']
        labels = {
            'total_value': '계약 총액',
            'guaranteed_ratio': '보장 비율 (0-1)',
            'years': '계약 연수',
            'start_year': '계약 시작 연도',
        }

    def clean_guaranteed_ratio(self):
        ratio = self.cleaned_data.get('guaranteed_ratio')
        if ratio is not None and (ratio < 0 or ratio > 1):
            raise forms.ValidationError('보장 비율은 0과 1 사이여야 합니다.')
        return ratio

    def clean_years(self):
        years = self.cleaned_data.get('years')
        if years is not None and years <= 0:
            raise forms.ValidationError('계약 연수는 0보다 커야 합니다.')
        return years


class PlayerWithContractForm(forms.ModelForm):
    """Combined form for adding a player with contract in one step."""

    total_value = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=Decimal('0'),
        label='계약 총액',
    )
    guaranteed_ratio = forms.DecimalField(
        max_digits=3,
        decimal_places=2,
        min_value=Decimal('0'),
        max_value=Decimal('1'),
        initial=Decimal('1.00'),
        label='보장 비율 (0-1)',
    )
    years = forms.IntegerField(min_value=1, label='계약 연수')
    start_year = forms.IntegerField(required=False, label='계약 시작 연도')

    class Meta:
        model = Player
        fields = ['name', 'position', 'jersey_number', 'years_to_retirement']
        labels = {
            'name': '이름',
            'position': '포지션',
            'jersey_number': '등번호',
            'years_to_retirement': '은퇴까지 남은 연수',
        }

    def save(self, commit=True):
        player = super().save(commit=commit)
        if commit:
            Contract.objects.create(
                player=player,
                total_value=self.cleaned_data['total_value'],
                guaranteed_ratio=self.cleaned_data['guaranteed_ratio'],
                years=self.cleaned_data['years'],
                start_year=self.cleaned_data.get('start_year'),
            )
        return player

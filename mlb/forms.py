from django import forms

from .models import MLBPlayer, ValuationSettings


class PlayerSearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='선수명',
        widget=forms.TextInput(attrs={'placeholder': '선수 이름 검색', 'class': 'form-control'}),
    )
    team = forms.CharField(
        required=False,
        label='팀',
        widget=forms.TextInput(attrs={'placeholder': '팀 필터', 'class': 'form-control'}),
    )
    position = forms.ChoiceField(
        required=False,
        label='포지션',
        choices=[('', '전체')] + list(MLBPlayer.POSITION_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class ValuationSettingsForm(forms.ModelForm):
    class Meta:
        model = ValuationSettings
        fields = ["valuation_method"]

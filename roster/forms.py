from decimal import Decimal

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model

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


class LoginForm(forms.Form):
    username = forms.CharField(label='아이디', max_length=150)
    password = forms.CharField(label='비밀번호', widget=forms.PasswordInput)

    error_messages = {
        'invalid_login': '아이디와 비밀번호를 다시 확인해주세요.',
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache


class SignupForm(forms.Form):
    username = forms.CharField(label='아이디', max_length=150)
    email = forms.EmailField(label='이메일')
    password = forms.CharField(label='비밀번호', widget=forms.PasswordInput)
    password_confirm = forms.CharField(label='비밀번호 확인', widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data['username']
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError('이미 사용 중인 아이디입니다.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email']
        user_model = get_user_model()
        if user_model.objects.filter(email=email).exists():
            raise forms.ValidationError('이미 사용 중인 이메일입니다.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('비밀번호가 일치하지 않습니다.')

        return cleaned_data

    def save(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
        )
        return user

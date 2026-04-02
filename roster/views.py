import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import ContractForm, LoginForm, PlayerForm, PlayerWithContractForm, SignupForm
from .models import Contract, Player


DEMO_USERNAME = 'jaewook8852'
DEMO_EMAIL = 'jaewook8852@naver.com'
DEMO_PASSWORD = 'asd123'


def ensure_demo_user():
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username=DEMO_USERNAME,
        defaults={'email': DEMO_EMAIL},
    )

    updated_fields = []
    if user.email != DEMO_EMAIL:
        user.email = DEMO_EMAIL
        updated_fields.append('email')

    if created or not user.check_password(DEMO_PASSWORD):
        user.set_password(DEMO_PASSWORD)
        updated_fields.append('password')

    if updated_fields:
        user.save()

    return user


def login_view(request):
    ensure_demo_user()

    if request.user.is_authenticated:
        return redirect('roster:player_list')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        messages.success(request, '로그인되었습니다.')
        return redirect('roster:player_list')

    return render(request, 'roster/login.html', {'form': form})


def signup_view(request):
    ensure_demo_user()

    if request.user.is_authenticated:
        return redirect('roster:player_list')

    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, '회원가입이 완료되었습니다.')
        return redirect('roster:player_list')

    return render(request, 'roster/signup.html', {'form': form})


@login_required
def logout_view(request):
    auth_logout(request)
    messages.success(request, '로그아웃되었습니다.')
    return redirect('roster:login')


class PlayerListView(LoginRequiredMixin, ListView):
    model = Player
    context_object_name = 'players'
    template_name = 'roster/player_list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = Player.objects.select_related('contract').all()
        status = self.request.GET.get('status')
        if status in ['pending', 'active', 'released']:
            qs = qs.filter(status=status)
        return qs


class PlayerDetailView(LoginRequiredMixin, DetailView):
    model = Player
    context_object_name = 'player'
    template_name = 'roster/player_detail.html'


class PlayerCreateView(LoginRequiredMixin, CreateView):
    model = Player
    form_class = PlayerWithContractForm
    template_name = 'roster/player_form.html'
    success_url = reverse_lazy('roster:player_list')

    def form_valid(self, form):
        form.instance.status = 'active'
        return super().form_valid(form)


class PlayerUpdateView(LoginRequiredMixin, UpdateView):
    model = Player
    form_class = PlayerForm
    context_object_name = 'player'
    template_name = 'roster/player_form.html'

    def get_success_url(self):
        return reverse_lazy('roster:player_detail', kwargs={'pk': self.object.pk})


@login_required
def player_kick_out(request, pk):
    player = get_object_or_404(Player, pk=pk)
    if request.method == 'POST':
        player.status = 'released'
        player.save()
        return redirect('roster:player_list')
    return redirect('roster:player_detail', pk=pk)


@login_required
def contract_edit(request, pk):
    player = get_object_or_404(Player, pk=pk)
    try:
        contract = Contract.objects.get(player=player)
    except Contract.DoesNotExist:
        contract = None

    if request.method == 'POST':
        form = ContractForm(request.POST, instance=contract)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.player = player
            obj.save()
            return redirect('roster:player_detail', pk=pk)
    else:
        form = ContractForm(instance=contract)

    return render(request, 'roster/contract_form.html', {'form': form, 'player': player})


def _serialize_contract(contract):
    if contract is None:
        return None

    return {
        'id': contract.pk,
        'total_value': float(contract.total_value),
        'guaranteed_ratio': float(contract.guaranteed_ratio),
        'years': contract.years,
        'start_year': contract.start_year,
        'guaranteed_amount': float(contract.guaranteed_amount),
        'net_worth': float(contract.net_worth),
    }


def _serialize_player(player):
    return {
        'id': player.pk,
        'name': player.name,
        'position': player.position,
        'jersey_number': player.jersey_number,
        'years_to_retirement': player.years_to_retirement,
        'status': player.status,
        'status_display': player.get_status_display(),
        'created_at': player.created_at.isoformat(),
        'updated_at': player.updated_at.isoformat(),
        'contract': _serialize_contract(getattr(player, 'contract', None)),
    }


def _json_error(message, *, status=400, errors=None):
    payload = {'message': message}
    if errors:
        payload['errors'] = errors
    return JsonResponse(payload, status=status)


def _serialize_user(user):
    return {
        'id': user.pk,
        'username': user.username,
        'email': user.email,
        'is_authenticated': user.is_authenticated,
    }


def _parse_json_body(request):
    if not request.body:
        return {}

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        raise ValidationError({'body': ['Invalid JSON body.']})

    if not isinstance(payload, dict):
        raise ValidationError({'body': ['JSON body must be an object.']})

    return payload


def _coerce_int(value, field_name, *, allow_null=False):
    if value in (None, ''):
        if allow_null:
            return None
        raise ValidationError({field_name: ['This field is required.']})

    if isinstance(value, bool):
        raise ValidationError({field_name: ['Enter a whole number.']})

    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({field_name: ['Enter a whole number.']})


def _coerce_decimal(value, field_name):
    if value in (None, ''):
        raise ValidationError({field_name: ['This field is required.']})

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError({field_name: ['Enter a valid number.']})


def _apply_player_payload(player, payload, *, partial):
    required_fields = {'name', 'position'}
    if not partial:
        missing_fields = required_fields - payload.keys()
        if missing_fields:
            raise ValidationError({field: ['This field is required.'] for field in sorted(missing_fields)})

    if 'name' in payload:
        player.name = payload['name']
    if 'position' in payload:
        player.position = payload['position']
    if 'status' in payload:
        player.status = payload['status']
    if 'jersey_number' in payload:
        player.jersey_number = _coerce_int(payload['jersey_number'], 'jersey_number', allow_null=True)
    if 'years_to_retirement' in payload:
        player.years_to_retirement = _coerce_int(
            payload['years_to_retirement'],
            'years_to_retirement',
            allow_null=True,
        )

    player.full_clean()
    player.save()
    return player


def _apply_contract_payload(player, payload, *, partial):
    if payload is None:
        Contract.objects.filter(player=player).delete()
        return None

    if not isinstance(payload, dict):
        raise ValidationError({'contract': ['Contract must be an object or null.']})

    try:
        contract = player.contract
        is_new = False
    except Contract.DoesNotExist:
        contract = Contract(player=player)
        is_new = True

    required_fields = {'total_value', 'guaranteed_ratio', 'years'}
    if is_new or not partial:
        missing_fields = required_fields - payload.keys()
        if missing_fields:
            raise ValidationError(
                {'contract': [f'Missing required contract fields: {", ".join(sorted(missing_fields))}.']}
            )

    if 'total_value' in payload:
        contract.total_value = _coerce_decimal(payload['total_value'], 'total_value')
    if 'guaranteed_ratio' in payload:
        contract.guaranteed_ratio = _coerce_decimal(payload['guaranteed_ratio'], 'guaranteed_ratio')
    if 'years' in payload:
        contract.years = _coerce_int(payload['years'], 'years')
    if 'start_year' in payload:
        contract.start_year = _coerce_int(payload['start_year'], 'start_year', allow_null=True)

    contract.full_clean()
    contract.save()
    return contract


@require_http_methods(['GET'])
def api_team_image(request):
    candidates = [
        ('ohtani.png', 'image/png'),
        ('ohtani.img', 'image/png'),
        ('ohtani.jpeg', 'image/jpeg'),
        ('ohtani.jpg', 'image/jpeg'),
    ]
    for filename, content_type in candidates:
        image_path = settings.BASE_DIR / filename
        if image_path.exists():
            return FileResponse(image_path.open('rb'), content_type=content_type)

    raise Http404('Ohtani image file not found.')


@csrf_exempt
@require_http_methods(['POST'])
def api_login(request):
    ensure_demo_user()

    try:
        payload = _parse_json_body(request)
    except ValidationError as exc:
        return _json_error('Invalid request body.', errors=exc.message_dict)

    form = LoginForm(request, data=payload)
    if not form.is_valid():
        return _json_error('Login failed.', errors=form.errors, status=400)

    user = form.get_user()
    login(request, user)
    return JsonResponse(
        {
            'message': '로그인되었습니다.',
            'user': _serialize_user(user),
        }
    )


@csrf_exempt
@require_http_methods(['POST'])
def api_signup(request):
    ensure_demo_user()

    try:
        payload = _parse_json_body(request)
    except ValidationError as exc:
        return _json_error('Invalid request body.', errors=exc.message_dict)

    form = SignupForm(data=payload)
    if not form.is_valid():
        return _json_error('Signup failed.', errors=form.errors, status=400)

    user = form.save()
    login(request, user)
    return JsonResponse(
        {
            'message': '회원가입이 완료되었습니다.',
            'user': _serialize_user(user),
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(['POST'])
def api_logout(request):
    if request.user.is_authenticated:
        auth_logout(request)
    return JsonResponse({'message': '로그아웃되었습니다.'})


@require_http_methods(['GET'])
def api_me(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                'is_authenticated': False,
                'user': None,
            },
            status=401,
        )

    return JsonResponse(
        {
            'is_authenticated': True,
            'user': _serialize_user(request.user),
        }
    )


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_players(request):
    if request.method == 'GET':
        players = Player.objects.select_related('contract').all()
        status = request.GET.get('status')
        valid_statuses = {choice for choice, _ in Player.STATUS_CHOICES}
        if status in valid_statuses:
            players = players.filter(status=status)

        serialized_players = [_serialize_player(player) for player in players]
        return JsonResponse({'count': len(serialized_players), 'players': serialized_players})

    try:
        payload = _parse_json_body(request)
    except ValidationError as exc:
        return _json_error('Invalid request body.', errors=exc.message_dict)

    contract_supplied = 'contract' in payload
    contract_payload = payload.pop('contract', None)

    try:
        with transaction.atomic():
            player = _apply_player_payload(Player(), payload, partial=False)
            if contract_supplied:
                _apply_contract_payload(player, contract_payload, partial=False)
            player.refresh_from_db()
    except ValidationError as exc:
        return _json_error('Validation failed.', errors=exc.message_dict)

    return JsonResponse(_serialize_player(player), status=201)


@csrf_exempt
@require_http_methods(['GET', 'PATCH', 'PUT', 'DELETE'])
def api_player_detail(request, pk):
    player = get_object_or_404(Player.objects.select_related('contract'), pk=pk)

    if request.method == 'GET':
        return JsonResponse(_serialize_player(player))

    if request.method == 'DELETE':
        player.delete()
        return HttpResponse(status=204)

    try:
        payload = _parse_json_body(request)
    except ValidationError as exc:
        return _json_error('Invalid request body.', errors=exc.message_dict)

    contract_supplied = 'contract' in payload
    contract_payload = payload.pop('contract', None)

    try:
        with transaction.atomic():
            player = _apply_player_payload(player, payload, partial=request.method == 'PATCH')
            if contract_supplied:
                _apply_contract_payload(player, contract_payload, partial=request.method == 'PATCH')
            player.refresh_from_db()
    except ValidationError as exc:
        return _json_error('Validation failed.', errors=exc.message_dict)

    return JsonResponse(_serialize_player(player))

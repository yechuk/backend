from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import ContractForm, PlayerForm, PlayerWithContractForm
from .models import Contract, Player


class PlayerListView(ListView):
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


class PlayerDetailView(DetailView):
    model = Player
    context_object_name = 'player'
    template_name = 'roster/player_detail.html'


class PlayerCreateView(CreateView):
    model = Player
    form_class = PlayerWithContractForm
    template_name = 'roster/player_form.html'
    success_url = reverse_lazy('roster:player_list')

    def form_valid(self, form):
        form.instance.status = 'active'
        return super().form_valid(form)


class PlayerUpdateView(UpdateView):
    model = Player
    form_class = PlayerForm
    context_object_name = 'player'
    template_name = 'roster/player_form.html'

    def get_success_url(self):
        return reverse_lazy('roster:player_detail', kwargs={'pk': self.object.pk})


def player_kick_out(request, pk):
    player = get_object_or_404(Player, pk=pk)
    if request.method == 'POST':
        player.status = 'released'
        player.save()
        return redirect('roster:player_list')
    return redirect('roster:player_detail', pk=pk)


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

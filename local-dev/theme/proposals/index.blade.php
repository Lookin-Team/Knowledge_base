@extends('layouts.base')
@section('content')
<div class="container medium py-xl"><div class="card content-wrap">
<h1>{{ $queue ? 'Запросы на публикацию' : 'Мои предложения' }}</h1>
<p><a class="button" href="{{ url('/publication-proposals/new') }}">Предложить публикацию</a>
@if(\Lookin\Proposals::moderator())
@if($queue)
<a class="button outline" href="{{ url('/publication-proposals') }}">Мои предложения</a>
@else
<a class="button outline" href="{{ url('/publication-proposals?queue=1') }}">Запросы на публикацию</a>
@endif
@endif</p>
@forelse($items as $proposal)
<div class="mb-m"><a href="{{ url('/publication-proposals/'.$proposal->id) }}">№{{ $proposal->id }} · {{ $proposal->title }}</a>
<p class="text-muted">{{ ['pending'=>'На рассмотрении','published'=>'Опубликовано','rejected'=>'Отклонено'][$proposal->status] }} · {{ $proposal->created_at }} · Автор №{{ $proposal->author_id }} · {{ $proposal->direction }} · {{ $proposal->hashtags }}</p></div>
@empty<p>Предложений пока нет.</p>@endforelse
{{ $items->links() }}
</div></div>
@endsection

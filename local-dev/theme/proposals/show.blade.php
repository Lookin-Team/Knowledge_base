@extends('layouts.base')
@section('content')
<div class="container medium py-xl"><div class="card content-wrap">
<a href="{{ url('/publication-proposals'.(\Lookin\Proposals::moderator() ? '?queue=1' : '')) }}">К списку предложений</a>
<h1>Заявка №{{ $item->id }}: {{ $item->title }}</h1>
<p>{{ ['pending'=>'На рассмотрении','published'=>'Опубликовано','rejected'=>'Отклонено'][$item->status] }} · Автор №{{ $item->author_id }} · {{ $item->created_at }}</p>
@if($errors->any())<div role="alert">{{ implode(' ', $errors->all()) }}</div>@endif
@if(\Lookin\Proposals::moderator() && $item->status === 'pending')
<form method="post" action="{{ url('/publication-proposals/'.$item->id) }}">@csrf
@include('proposals.fields')
@include('proposals.files', ['selectFiles' => true])
<div class="form-group"><label for="book_id">Книга для публикации</label><select id="book_id" name="book_id"><option value="">Выберите книгу</option>@foreach($books as $book)<option value="{{ $book->id }}" @selected((string)old('book_id') === (string)$book->id)>{{ $book->name }}</option>@endforeach</select></div>
<div class="form-group"><label for="reason">Комментарий / причина отклонения</label><textarea id="reason" name="reason" maxlength="2000">{{ old('reason') }}</textarea></div>
<button class="button outline" name="action" value="save">Сохранить правки</button>
<button class="button" name="action" value="publish">Опубликовать</button>
<button class="button outline" name="action" value="reject" formnovalidate>Отклонить</button>
</form>
@else
@include('proposals.files', ['selectFiles' => false])
<h2>{{ $item->title }}</h2><div class="text-wrap">{!! nl2br(e($item->body)) !!}</div>
<p>Направление: {{ $item->direction }} · Хэштеги: {{ $item->hashtags }}</p>
@if($item->reason)<p>Комментарий: {{ $item->reason }}</p>@endif
@if($page)<p><a href="{{ $page->getUrl() }}">Открыть опубликованную страницу</a></p>@endif
@endif
@if(\Lookin\Proposals::moderator())<details><summary>Исходная заявка автора</summary><pre class="text-wrap">{{ json_encode(json_decode($item->original), JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT) }}</pre></details>@endif
</div></div>
@endsection

@extends('layouts.base')
@section('content')
<div class="container medium py-xl"><div class="card content-wrap">
<h1>Предложить публикацию</h1><p>После отправки публикация появится у модератора. Он сможет отредактировать её, опубликовать или отклонить.</p>
@if($errors->any())<div role="alert">{{ implode(' ', $errors->all()) }}</div>@endif
<form enctype="multipart/form-data" method="post" action="{{ url('/publication-proposals') }}">@csrf
@include('proposals.fields')
<div class="form-group"><label for="files">Картинки и документы</label><input type="file" id="files" name="files[]" multiple accept=".jpg,.jpeg,.png,.webp,.gif,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv"><p>До 5 файлов по 2 МБ. До публикации доступны только вам и модератору. После ошибки формы файлы нужно выбрать заново.</p></div>
<button class="button" type="submit">Отправить на рассмотрение</button>
<a class="button outline" href="{{ url('/publication-proposals') }}">Мои предложения</a>
</form></div></div>
@endsection

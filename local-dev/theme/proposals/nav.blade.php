@if(class_exists(\Lookin\Proposals::class) && \Lookin\Proposals::allowed())
<a class="lk-nav-item" href="{{ url('/publication-proposals/new') }}">@icon('edit') Предложить публикацию</a>
<a class="lk-nav-item" href="{{ url('/publication-proposals') }}">@icon('contents') Мои предложения</a>
@if(\Lookin\Proposals::moderator())
<a class="lk-nav-item" href="{{ url('/publication-proposals?queue=1') }}">@icon('list') Запросы на публикацию</a>
@endif
@endif

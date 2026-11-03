@if($files->isNotEmpty())
<section class="mb-l" aria-label="Файлы заявки"><h2>Картинки и документы</h2>
@if($selectFiles)<p>Отметьте файлы, которые нужно приложить к опубликованной статье.</p>@endif
@foreach($files as $file)
<div class="mb-m">
@if($selectFiles)<label><input type="checkbox" name="publish_files[]" value="{{ $file->id }}" @checked(in_array((string)$file->id, array_map('strval', old('publish_files', $files->pluck('id')->all())), true))> Приложить к статье</label>@endif
<a href="{{ url('/publication-proposals/'.$item->id.'/files/'.$file->id) }}">{{ $file->name }}</a> ({{ number_format($file->size / 1024, 0) }} КБ)
@if(in_array($file->mime, ['image/jpeg','image/png','image/webp','image/gif'], true))
<div><img src="{{ url('/publication-proposals/'.$item->id.'/files/'.$file->id.'?preview=1') }}" alt="{{ $file->name }}" style="max-width:100%;max-height:240px;object-fit:contain" loading="lazy"></div>
@endif
</div>
@endforeach
</section>
@endif

<div class="form-group"><label for="kind">Тип публикации</label><select name="kind" id="kind" required>
@foreach(['news'=>'Новость','instruction'=>'Инструкция','other'=>'Другое'] as $value=>$label)
<option value="{{ $value }}" @selected(old('kind', $item->kind ?? 'news') === $value)>{{ $label }}</option>
@endforeach
</select></div>
<div class="form-group"><label for="title">Заголовок</label><input type="text" id="title" name="title" required maxlength="255" value="{{ old('title', $item->title ?? '') }}"></div>
<div class="form-group"><label for="body">Текст публикации</label><textarea style="width:100%;min-height:240px" id="body" name="body" required maxlength="15000" rows="14">{{ old('body', $item->body ?? '') }}</textarea><p class="text-muted">Обычный текст. При публикации сохраняются переносы строк.</p></div>
<div class="form-group"><label for="shelf_id">Желаемая полка</label><select id="shelf_id" name="shelf_id"><option value="">Без полки</option>
@foreach($shelves as $shelf)<option value="{{ $shelf->id }}" @selected((string)old('shelf_id', $item->shelf_id ?? '') === (string)$shelf->id)>{{ $shelf->name }}</option>@endforeach
</select></div>
<div class="form-group"><label for="direction">Направление (обязательно, если полка не выбрана)</label><input type="text" id="direction" name="direction" maxlength="255" value="{{ old('direction', $item->direction ?? '') }}"></div>
<div class="form-group"><label for="hashtags">Хэштеги</label><input type="text" id="hashtags" name="hashtags" maxlength="1000" placeholder="#команда #обучение" value="{{ old('hashtags', $item->hashtags ?? '') }}"><p class="text-muted">До 20 хэштегов, через пробел или запятую.</p></div>

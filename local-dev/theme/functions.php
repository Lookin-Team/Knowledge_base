<?php

require_once __DIR__ . '/proposals/Proposals.php';
\BookStack\Facades\Theme::listen(\BookStack\Theming\ThemeEvents::APP_BOOT, function () {
    \Illuminate\Support\Facades\Route::middleware(['web', 'auth', 'guard:standard', 'throttle:60,1'])
        ->prefix('publication-proposals')->group(function () {
            $controller = \Lookin\Proposals::class;
            \Illuminate\Support\Facades\Route::get('/', [$controller, 'index']);
            \Illuminate\Support\Facades\Route::get('/new', [$controller, 'create']);
            \Illuminate\Support\Facades\Route::post('/', [$controller, 'store'])->middleware('throttle:10,1');
            \Illuminate\Support\Facades\Route::get('/{id}/files/{fileId}', [$controller, 'download'])->whereNumber(['id', 'fileId']);
            \Illuminate\Support\Facades\Route::get('/{id}', [$controller, 'show'])->whereNumber('id');
            \Illuminate\Support\Facades\Route::post('/{id}', [$controller, 'decide'])->whereNumber('id')->middleware('throttle:10,1');
        });
});

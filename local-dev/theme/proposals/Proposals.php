<?php
namespace Lookin;

use BookStack\Entities\Queries\EntityQueries;
use BookStack\Entities\Repos\PageRepo;
use BookStack\Http\Controller;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class Proposals extends Controller
{
    public static function ids(string $key): array
    {
        return array_values(array_filter(array_map('intval', explode(',', (string) config('lookin_proposals.' . $key, env($key, ''))))));
    }

    public static function moderator(): bool
    {
        return auth()->check() && user()->hasAppAccess() && in_array((int) user()->id, self::ids('LOOKIN_PROPOSAL_MODERATOR_IDS'), true);
    }

    public static function allowed(): bool
    {
        return auth()->check() && user()->hasAppAccess() && (self::moderator() || in_array((int) user()->id, self::ids('LOOKIN_PROPOSAL_AUTHOR_IDS'), true));
    }

    private function access(): void
    {
        abort_unless(self::allowed(), 403);
    }

    private function table()
    {
        return DB::table('lookin_publication_proposals');
    }

    private function proposal(int $id, bool $lock = false)
    {
        $query = $this->table()->where('id', $id);
        if (!self::moderator()) {
            $query->where('author_id', user()->id);
        }
        $row = ($lock ? $query->lockForUpdate() : $query)->first();
        abort_unless($row, 404);
        return $row;
    }

    public function index(Request $request)
    {
        $this->access();
        $queue = self::moderator() && $request->query('queue') === '1';
        $query = $this->table();
        if (!$queue) {
            $query->where('author_id', user()->id);
        }
        return view('proposals.index', ['items' => $query->orderByDesc('id')->paginate(25)->withQueryString(), 'queue' => $queue]);
    }

    public function create()
    {
        $this->access();
        return view('proposals.form', ['shelves' => app(EntityQueries::class)->shelves->visibleForList()->orderBy('name')->get()]);
    }

    private function fields(Request $request): array
    {
        $data = $request->validate([
            'kind' => 'required|in:news,instruction,other', 'title' => 'required|string|max:255',
            'body' => 'required|string|max:15000', 'shelf_id' => 'nullable|integer|min:1',
            'direction' => 'nullable|required_without:shelf_id|string|max:255',
            'hashtags' => 'nullable|string|max:1000',
        ]);
        if (!empty($data['shelf_id'])) {
            abort_unless(app(EntityQueries::class)->shelves->findVisibleById((int) $data['shelf_id']), 422);
        }
        $tags = preg_split('/[\s,#]+/u', $data['hashtags'] ?? '', -1, PREG_SPLIT_NO_EMPTY);
        abort_if(count($tags) > 20 || count(array_filter($tags, fn ($tag) => mb_strlen($tag) > 80)) > 0, 422, 'Максимум 20 хэштегов, каждый до 80 символов.');
        return array_merge($data, ['shelf_id' => ($data['shelf_id'] ?? null) ?: null, 'direction' => $data['direction'] ?? '', 'hashtags' => implode(' ', array_unique($tags))]);
    }

    public function store(Request $request)
    {
        $this->access();
        $data = $this->fields($request);
        $uploads = $this->validatedUploads($request);
        $id = DB::transaction(function () use ($data, $uploads) {
            $id = $this->table()->insertGetId(array_merge($data, [
                'author_id' => user()->id, 'status' => 'pending', 'original' => json_encode($data, JSON_UNESCAPED_UNICODE),
                'created_at' => now(), 'updated_at' => now(),
            ]));
            foreach ($uploads as $file) {
                DB::table('lookin_proposal_files')->insert([
                    'proposal_id' => $id, 'name' => basename(str_replace('\\', '/', $file->getClientOriginalName())),
                    'mime' => (new \finfo(FILEINFO_MIME_TYPE))->file($file->getRealPath()), 'size' => $file->getSize(),
                    'content' => base64_encode(file_get_contents($file->getRealPath())), 'created_at' => now(),
                ]);
            }
            return $id;
        });
        return redirect('/publication-proposals/' . $id);
    }

    public function show(int $id)
    {
        $this->access();
        $item = $this->proposal($id);
        $queries = app(EntityQueries::class);
        $page = $item->page_id ? $queries->pages->findVisibleById($item->page_id) : null;
        return view('proposals.show', [
            'item' => $item, 'page' => $page,
            'files' => DB::table('lookin_proposal_files')->where('proposal_id', $id)->select('id', 'name', 'mime', 'size', 'attachment_id')->get(),
            'books' => self::moderator() ? $queries->books->visibleForList()->get()->filter(fn ($b) => userCan('page-create', $b)) : collect(),
            'shelves' => $queries->shelves->visibleForList()->orderBy('name')->get(),
        ]);
    }

    public function decide(Request $request, int $id)
    {
        $this->access();
        abort_unless(self::moderator(), 403);
        $action = $request->validate(['action' => 'required|in:save,reject,publish'])['action'];
        $data = $action === 'reject' ? [] : $this->fields($request);
        $reason = $request->validate(['reason' => ($action === 'reject' ? 'required' : 'nullable') . '|string|max:2000'])['reason'] ?? '';
        // PageRepo uses DatabaseTransaction too. Set isolation before opening the outer transaction.
        DB::statement('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED');
        $createdPaths = [];
        try {
        DB::transaction(function () use ($request, $id, $action, $data, $reason, &$createdPaths) {
            $row = $this->proposal($id, true);
            abort_unless($row->status === 'pending', 409, 'По этой заявке решение уже принято.');
            $updates = array_merge($data, ['updated_at' => now()]);
            if ($action === 'publish') {
                $input = $request->validate(['book_id' => 'required|integer|min:1']);
                $book = app(EntityQueries::class)->books->findVisibleById((int) $input['book_id']);
                abort_unless($book && userCan('page-create', $book), 403);
                $repo = app(PageRepo::class);
                $draft = $repo->getNewDraftPage($book);
                $tags = array_map(fn ($tag) => ['name' => $tag, 'value' => ''], preg_split('/\s+/u', $data['hashtags'], -1, PREG_SPLIT_NO_EMPTY));
                $page = $repo->publishDraft($draft, ['name' => $data['title'], 'html' => '<p>' . nl2br(e($data['body'])) . '</p>', 'tags' => $tags, 'changelog' => 'Публикация по заявке №' . $id]);
                $this->publishFiles($request, $id, $page, $createdPaths);
                $updates['page_id'] = $page->id;
                $updates['status'] = 'published';
            } elseif ($action === 'reject') {
                $updates['status'] = 'rejected';
            }
            if ($action !== 'save') {
                $updates['moderator_id'] = user()->id;
                $updates['decided_at'] = now();
                $updates['reason'] = $reason;
            }
            $this->table()->where('id', $id)->update($updates);
        });
        } catch (\Throwable $error) {
            foreach ($createdPaths as $path) {
                app(\BookStack\Uploads\FileStorage::class)->delete($path);
            }
            throw $error;
        }
        return redirect('/publication-proposals/' . $id);
    }
    private function validatedUploads(Request $request): array
    {
        $request->validate([
            'files' => 'nullable|array|max:5',
            'files.*' => 'required|file|max:2048|mimes:jpg,jpeg,png,webp,gif,pdf,doc,docx,xls,xlsx,ppt,pptx,txt,csv',
        ]);
        $files = $request->file('files', []);
        $extensions = ['jpg','jpeg','png','webp','gif','pdf','doc','docx','xls','xlsx','ppt','pptx','txt','csv'];
        foreach ($files as $index => $file) {
            // Validate both the real content and the supplied extension. Never serve active HTML/SVG.
            $mime = (new \finfo(FILEINFO_MIME_TYPE))->file($file->getRealPath());
            $ext = strtolower($file->getClientOriginalExtension());
            $types = [
                'jpg'=>['image/jpeg'], 'jpeg'=>['image/jpeg'], 'png'=>['image/png'],
                'webp'=>['image/webp'], 'gif'=>['image/gif'], 'pdf'=>['application/pdf'],
                'txt'=>['text/plain'], 'csv'=>['text/plain','text/csv','application/csv'],
                'doc'=>['application/msword','application/x-ole-storage','application/CDFV2'],
                'xls'=>['application/vnd.ms-excel','application/x-ole-storage','application/CDFV2'],
                'ppt'=>['application/vnd.ms-powerpoint','application/x-ole-storage','application/CDFV2'],
                'docx'=>['application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/zip'],
                'xlsx'=>['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/zip'],
                'pptx'=>['application/vnd.openxmlformats-officedocument.presentationml.presentation','application/zip'],
            ];
            $valid = in_array($mime, $types[$ext] ?? [], true);
            if ($valid && in_array($ext, ['docx','xlsx','pptx'], true)) {
                $zip = new \ZipArchive();
                $valid = $zip->open($file->getRealPath()) === true;
                if ($valid) {
                    $entry = ['docx'=>'word/document.xml','xlsx'=>'xl/workbook.xml','pptx'=>'ppt/presentation.xml'][$ext];
                    $valid = $zip->locateName('[Content_Types].xml') !== false && $zip->locateName($entry) !== false;
                    $zip->close();
                }
            }
            if (!$valid) {
                throw \Illuminate\Validation\ValidationException::withMessages(['files.' . $index => 'Формат файла не поддерживается или не соответствует его расширению.']);
            }

            if (!in_array(strtolower($file->getClientOriginalExtension()), $extensions, true)) {
                throw \Illuminate\Validation\ValidationException::withMessages(['files.' . $index => 'Этот формат файла не поддерживается.']);
            }
            abort_if(mb_strlen($file->getClientOriginalName()) > 255 || preg_match('/[\x00-\x1f\x7f]/', $file->getClientOriginalName()), 422);
        }
        return $files;
    }

    public function download(Request $request, int $id, int $fileId)
    {
        $this->access();
        $this->proposal($id);
        $file = DB::table('lookin_proposal_files')->where('proposal_id', $id)->where('id', $fileId)->first();
        abort_unless($file, 404);
        $image = in_array($file->mime, ['image/jpeg','image/png','image/webp','image/gif'], true);
        $inline = $image && $request->query('preview') === '1';
        $response = response(base64_decode($file->content, true), 200, [
            'Content-Type' => $inline ? $file->mime : 'application/octet-stream',
            'X-Content-Type-Options' => 'nosniff', 'Cache-Control' => 'private, no-store',
            'Content-Security-Policy' => "default-src 'none'; sandbox",
        ]);
        $response->headers->set('Content-Disposition', $response->headers->makeDisposition($inline ? 'inline' : 'attachment', $file->name, 'file'));
        return $response;
    }

    private function publishFiles(Request $request, int $id, $page, array &$createdPaths): void
    {
        $data = $request->validate(['publish_files' => 'nullable|array|max:5', 'publish_files.*' => 'integer|min:1']);
        $ids = array_unique(array_map('intval', $data['publish_files'] ?? []));
        if (!$ids) {
            return;
        }
        abort_unless(userCan('attachment-create-all') && userCan('page-update', $page), 403);
        $files = DB::table('lookin_proposal_files')->where('proposal_id', $id)->whereIn('id', $ids)->get();
        abort_unless($files->count() === count($ids), 422);
        foreach ($files as $file) {
            $temp = tempnam(sys_get_temp_dir(), 'proposal-');
            try {
                file_put_contents($temp, base64_decode($file->content, true));
                $upload = new \Symfony\Component\HttpFoundation\File\UploadedFile($temp, $file->name, $file->mime, null, true);
                // Store through the normal BookStack attachment service, preserving page permissions.
                $attachment = app(\BookStack\Uploads\AttachmentService::class)->saveNewUpload($upload, $page->id);
                $createdPaths[] = $attachment->path;
                DB::table('lookin_proposal_files')->where('id', $file->id)->update(['attachment_id' => $attachment->id]);
            } finally {
                if (is_file($temp)) { unlink($temp); }
            }
        }
    }

}

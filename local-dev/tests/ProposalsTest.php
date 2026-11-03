<?php
namespace Tests\Local;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Env;
use Illuminate\Support\Facades\Schema;
use Tests\TestCase;

class ProposalsTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        config(['lookin_proposals.LOOKIN_PROPOSAL_AUTHOR_ROLE_IDS' => '']);
        $this->assertSame('mysql_testing', config('database.default'));
        if (!Schema::hasTable('lookin_publication_proposals')) {
            Schema::create('lookin_publication_proposals', function ($t) {
                $t->bigIncrements('id'); $t->unsignedInteger('author_id'); $t->string('kind'); $t->string('title');
                $t->longText('body'); $t->unsignedInteger('shelf_id')->nullable(); $t->string('direction');
                $t->text('hashtags'); $t->longText('original'); $t->string('status');
                $t->unsignedInteger('moderator_id')->nullable(); $t->unsignedInteger('page_id')->nullable();
                $t->text('reason')->nullable(); $t->timestamp('decided_at')->nullable(); $t->timestamps();
            });
        }
        config(['lookin_proposals.LOOKIN_PROPOSAL_MODERATOR_IDS' => (string)$this->users->admin()->id]);
        config(['lookin_proposals.LOOKIN_PROPOSAL_AUTHOR_IDS' => (string)$this->users->viewer()->id]);
    }

    private function fields(): array
    {
        return ['kind'=>'instruction','title'=>'Synthetic proposal','body'=>'<script>alert(1)</script>','direction'=>'IT','shelf_id'=>'','hashtags'=>'#team #guide'];
    }

    public function test_submission_is_private_and_does_not_grant_page_permissions(): void
    {
        $this->asViewer();
        $this->get('/publication-proposals/new')->assertOk()->assertSee('Предложить публикацию');
        $this->post('/publication-proposals', $this->fields())->assertRedirect();
        $id=DB::table('lookin_publication_proposals')->max('id');
        $this->get('/publication-proposals/'.$id)->assertOk()->assertDontSee('<script>alert(1)</script>', false);
        $this->post('/publication-proposals/'.$id, ['action'=>'reject','reason'=>'No'])->assertForbidden();
        $other=$this->users->newUser();
        config(['lookin_proposals.LOOKIN_PROPOSAL_AUTHOR_IDS' => (string)$other->id]);
        $this->actingAs($other)->get('/publication-proposals/'.$id)->assertNotFound();
        config(['lookin_proposals.LOOKIN_PROPOSAL_AUTHOR_IDS' => '']);
        $this->get('/publication-proposals')->assertForbidden();
    }

    public function test_moderator_edits_publishes_once_and_preserves_original(): void
    {
        $this->asViewer();
        $this->post('/publication-proposals', $this->fields())->assertRedirect();
        $id=DB::table('lookin_publication_proposals')->max('id');
        $this->asAdmin();
        $this->get('/publication-proposals?queue=1')->assertOk();
        $this->get('/publication-proposals/'.$id)->assertOk();
        $data=array_merge($this->fields(),['title'=>'Edited title','action'=>'save']);
        $this->post('/publication-proposals/'.$id,$data)->assertRedirect();
        $book=$this->entities->book();
        $data['action']='publish'; $data['book_id']=$book->id;
        $this->post('/publication-proposals/'.$id,$data)->assertRedirect();
        $row=DB::table('lookin_publication_proposals')->find($id);
        $this->assertSame('published',$row->status);
        $this->assertStringContainsString('Synthetic proposal',$row->original);
        $page=\BookStack\Entities\Models\Page::findOrFail($row->page_id);
        $this->assertSame('Edited title',$page->name);
        $this->assertStringNotContainsString('<script>', $page->html);
        $this->assertCount(2,$page->tags);
        $this->post('/publication-proposals/'.$id,$data)->assertStatus(409);
    }

    public function test_validation_rejection_and_guest_access(): void
    {
        $this->get('/publication-proposals')->assertRedirect();
        $this->asViewer();
        $data=$this->fields(); $data['direction']='';
        $this->post('/publication-proposals',$data)->assertSessionHasErrors('direction');
        $this->post('/publication-proposals',$this->fields())->assertRedirect();
        $id=DB::table('lookin_publication_proposals')->max('id');
        $this->asAdmin();
        $this->post('/publication-proposals/'.$id,['action'=>'reject','reason'=>'Нужно дополнить'])->assertRedirect();
        $this->asViewer();
        $this->get('/publication-proposals/'.$id)->assertOk()->assertSee('Нужно дополнить');
    }
    public function test_hidden_shelf_and_restricted_book_are_rejected(): void
    {
        $shelf=$this->entities->shelf();
        $book=$this->entities->book();
        $this->permissions->setEntityPermissions($shelf);
        $this->asViewer();
        $this->assertFalse(userCan('page-create', $book));
        $this->get('/publication-proposals/new')->assertOk()->assertDontSee($shelf->name);
        $data=$this->fields(); $data['shelf_id']=$shelf->id;
        $this->post('/publication-proposals',$data)->assertStatus(422);
        $this->post('/publication-proposals',$this->fields())->assertRedirect();
        $id=DB::table('lookin_publication_proposals')->max('id');
        // A moderator allowlist grants queue access, never BookStack creation rights.
        config(['lookin_proposals.LOOKIN_PROPOSAL_MODERATOR_IDS' => (string)user()->id]);
        $data=$this->fields(); $data['action']='publish'; $data['book_id']=$book->id;
        $this->post('/publication-proposals/'.$id,$data)->assertForbidden();
        $this->assertSame('pending',DB::table('lookin_publication_proposals')->find($id)->status);
    }

    public function test_private_image_and_document_upload_and_publication(): void
    {
        $this->asViewer();
        $png = base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=');
        $data=$this->fields();
        $data['files']=[
            \Illuminate\Http\UploadedFile::fake()->createWithContent('guide.txt', 'Synthetic document'),
            \Illuminate\Http\UploadedFile::fake()->createWithContent('image.png', $png),
        ];
        $this->post('/publication-proposals', $data)->assertRedirect();
        $id=DB::table('lookin_publication_proposals')->max('id');
        $files=DB::table('lookin_proposal_files')->where('proposal_id',$id)->orderBy('id')->get();
        $this->assertCount(2,$files);
        $url='/publication-proposals/'.$id.'/files/'.$files[0]->id;
        $this->get($url)->assertOk()->assertContent('Synthetic document')->assertHeader('X-Content-Type-Options','nosniff');
        $this->get('/publication-proposals/'.$id.'/files/'.$files[1]->id.'?preview=1')->assertOk()->assertHeader('Content-Type','image/png')->assertContent($png);
        $this->get('/publication-proposals/'.$id)->assertOk()->assertSee('guide.txt');
        $other=$this->users->newUser();
        config(['lookin_proposals.LOOKIN_PROPOSAL_AUTHOR_IDS' => (string)$other->id]);
        $this->actingAs($other)->get($url)->assertNotFound();
        $this->asAdmin();
        $this->get($url)->assertOk();
        $book=$this->entities->book();
        $this->permissions->setEntityPermissions($book);
        $publish=array_merge($this->fields(),['action'=>'publish','book_id'=>$book->id,'publish_files'=>[$files[0]->id]]);
        $this->post('/publication-proposals/'.$id,$publish)->assertRedirect();
        $file=DB::table('lookin_proposal_files')->find($files[0]->id);
        $attachment=\BookStack\Uploads\Attachment::findOrFail($file->attachment_id);
        try {
            $this->assertSame('guide.txt',$attachment->name);
            $this->assertSame(DB::table('lookin_publication_proposals')->find($id)->page_id,$attachment->uploaded_to);
            $stream=app(\BookStack\Uploads\AttachmentService::class)->streamAttachmentFromStorage($attachment);
            $this->assertSame('Synthetic document',stream_get_contents($stream)); fclose($stream);
            $this->assertNull(DB::table('lookin_proposal_files')->find($files[1]->id)->attachment_id);
            $this->post('/publication-proposals/'.$id,$publish)->assertStatus(409);
            $this->asViewer();
            $this->get($attachment->getUrl())->assertNotFound();
        } finally {
            app(\BookStack\Uploads\AttachmentService::class)->deleteFile($attachment);
        }
    }

    public function test_disallowed_and_oversized_files_are_rejected_atomically(): void
    {
        $this->asViewer();
        $before=DB::table('lookin_publication_proposals')->count();
        foreach (['evil.php'=>'<?php echo 1;', 'fake.png'=>'<html>fake image</html>', 'vector.svg'=>'<svg></svg>'] as $name=>$body) {
            $data=$this->fields(); $data['files']=[\Illuminate\Http\UploadedFile::fake()->createWithContent($name,$body)];
            $this->post('/publication-proposals',$data)->assertSessionHasErrors('files.0');
        }
        $data=$this->fields(); $data['files']=[\Illuminate\Http\UploadedFile::fake()->create('large.pdf',2049,'application/pdf')];
        $this->post('/publication-proposals',$data)->assertSessionHasErrors('files.0');
        $data['files']=array_map(fn($i)=>\Illuminate\Http\UploadedFile::fake()->createWithContent('file'.$i.'.txt','hello'),range(1,6));
        $this->post('/publication-proposals',$data)->assertSessionHasErrors('files');
        $this->assertSame($before,DB::table('lookin_publication_proposals')->count());
    }

    public function test_employee_role_automatically_allows_new_accounts_without_moderation(): void
    {
        config(['lookin_proposals.LOOKIN_PROPOSAL_AUTHOR_IDS' => '',
            'lookin_proposals.LOOKIN_PROPOSAL_AUTHOR_ROLE_IDS' => implode(',', $this->users->viewer()->roles->pluck('id')->all())]);
        $this->asViewer();
        $this->get('/publication-proposals/new')->assertOk();
        $new=$this->users->newUser();
        $new->roles()->sync($this->users->viewer()->roles->pluck('id')->all());
        $this->actingAs($new);
        $this->assertTrue(\Lookin\Proposals::allowed());
        $this->assertFalse(\Lookin\Proposals::moderator());
        $this->post('/publication-proposals',$this->fields())->assertRedirect();
        $this->assertFalse(userCan('page-create',$this->entities->book()));
        $new->roles()->sync([]); $new->load('roles');
        $this->assertFalse(\Lookin\Proposals::allowed());
    }

}

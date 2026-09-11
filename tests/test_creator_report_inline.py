import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.library_assets import _safe_internal_url

CID = 'clone_' + 'a' * 32
BASE = f'/api/creator-clone/sets/{CID}/files/'


def saved_report(set_id=CID, text='真实内容测试 <details><summary>公式</summary>末尾风险</details>'):
    directory = settings.creator_clones_dir / set_id
    directory.mkdir(parents=True)
    (directory / 'creator_clone.html').write_text('<!doctype html><meta charset="utf-8">' + text)
    (directory / 'creator_clone_result.json').write_text('{"summary":"saved"}')
    (directory / 'samples.json').write_text('{"samples":[],"selected_sample_ids":[]}')
    return directory


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob('*') if p.is_file()}


def test_inline_and_download_keep_identical_saved_content_and_state(monkeypatch):
    from app.services import creator_clone
    monkeypatch.setattr(creator_clone, 'ensure_creator_clone_html_report', lambda *_: pytest.fail('must not generate'))
    directory = saved_report()
    before = snapshot(settings.output_dir)
    client = TestClient(app)
    inline = client.get(BASE + 'creator_clone.html?view=1')
    download = client.get(BASE + 'creator_clone.html')
    assert inline.status_code == download.status_code == 200
    assert inline.content == download.content == (directory / 'creator_clone.html').read_bytes()
    assert inline.headers['content-type'] == 'text/html; charset=utf-8'
    assert inline.headers['content-disposition'] == 'inline; filename="creator_clone.html"'
    assert download.headers['content-disposition'] == 'attachment; filename="creator_clone.html"'
    assert inline.headers['cache-control'] == 'no-store'
    assert inline.headers['x-content-type-options'] == 'nosniff'
    csp = inline.headers['content-security-policy']
    assert 'sandbox;' in csp and "default-src 'none'" in csp
    assert 'allow-scripts' not in csp and 'allow-same-origin' not in csp
    assert snapshot(settings.output_dir) == before


def test_two_creators_never_share_report():
    saved_report(text='Alpha report')
    other = 'clone_' + 'b'*32
    saved_report(other, 'Beta report')
    client = TestClient(app)
    assert 'Alpha report' in client.get(BASE+'creator_clone.html?view=1').text
    assert 'Beta report' in client.get(f'/api/creator-clone/sets/{other}/files/creator_clone.html?view=1').text


def test_missing_html_does_not_generate_or_create_directory():
    client = TestClient(app)
    before = snapshot(settings.output_dir)
    for suffix in ['?view=1','']:
        response = client.get(BASE+'creator_clone.html'+suffix)
        assert response.status_code == 404
        assert '缺失' in response.json()['message']
    assert not (settings.creator_clones_dir / CID).exists()
    assert snapshot(settings.output_dir) == before
    d = settings.creator_clones_dir / CID
    d.mkdir()
    (d/'creator_clone.md').write_text('# Only Markdown')
    before = snapshot(settings.output_dir)
    assert client.get(BASE+'creator_clone.html?view=1').status_code == 404
    response = client.get(BASE+'creator_clone.md')
    assert response.status_code == 200 and response.headers['content-disposition'].startswith('attachment')
    assert snapshot(settings.output_dir) == before


@pytest.mark.parametrize('filename',['creator_clone.md','samples.json','distill_prompt.md','creator_clone_result.json'])
def test_non_html_view_rejected_download_preserved(filename):
    directory = saved_report()
    (directory/filename).write_text('{}' if filename.endswith('.json') else 'text')
    client = TestClient(app)
    assert client.get(BASE+filename+'?view=1').status_code == 400
    response = client.get(BASE+filename)
    assert response.status_code == 200 and response.headers['content-disposition'].startswith('attachment')


@pytest.mark.parametrize('query',['view=0','view=true','view=1&x=1','view=1&view=1','view=%31','view='])
def test_only_exact_view_parameter(query):
    saved_report()
    assert TestClient(app).get(BASE+'creator_clone.html?'+query).status_code == 400
    assert _safe_internal_url(BASE+'creator_clone.html?'+query) == ''


@pytest.mark.parametrize('set_id',['invalid','clone_..','clone_%2e%2e','clone_a%2fb','clone_'+ 'a'*96])
def test_invalid_report_identifier(set_id):
    client = TestClient(app)
    before = snapshot(settings.output_dir)
    response = client.get(f'/api/creator-clone/sets/{set_id}/files/creator_clone.html?view=1')
    assert response.status_code in {400,404}
    assert str(settings.output_dir) not in response.text
    assert snapshot(settings.output_dir) == before


def test_symlink_and_oversized_html_are_rejected(tmp_path):
    directory = saved_report()
    html = directory/'creator_clone.html'
    html.unlink()
    outside = tmp_path/'outside.html'; outside.write_text('PRIVATE')
    html.symlink_to(outside)
    client=TestClient(app)
    assert client.get(BASE+'creator_clone.html?view=1').status_code == 403
    html.unlink()
    with html.open('wb') as stream:
        stream.truncate(8*1024*1024+1)
    assert client.get(BASE+'creator_clone.html?view=1').status_code == 413
    other = settings.creator_clones_dir / ('clone_'+'c'*32)
    other.symlink_to(directory, target_is_directory=True)
    assert client.get(f'/api/creator-clone/sets/{other.name}/files/creator_clone.html?view=1').status_code == 403


def test_safe_library_url_allows_only_report_view():
    assert _safe_internal_url(BASE+'creator_clone.html?view=1') == BASE+'creator_clone.html?view=1'
    assert not _safe_internal_url(BASE+'samples.json?view=1')
    assert not _safe_internal_url('https://example.test'+BASE+'creator_clone.html?view=1')

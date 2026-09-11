import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import CaseArtifact
from app.services import creator_clone as clone
from app.services.creator_covers import attach_frame_previews, validated_cover_url
from app.services.local_chrome import _handoff_sample, _sample_from_browser_item

SIGNED = 'https://p3-pc-sign.douyinpic.com/tos-cn-i-dy/object%2Babc~tplv-dy-cropcenter:323:430.jpeg?x-signature=abc%2Fxyz+ABC%3D&x-expires=2000000000&token=image-token&format=jpeg'
AID = '7641985646235536703'
CID = 'case_' + 'a' * 32


def make_case(case_id=CID, aweme_id=AID):
    directory = settings.cases_dir / case_id / 'keyframes'
    directory.mkdir(parents=True)
    for name in ['frame_0001_01.00s.jpg', 'frame_0000_00.00s.jpg']:
        Image.new('RGB', (32, 24), 'green').save(directory / name)
    artifact = CaseArtifact(case_id=case_id, aweme_id=aweme_id, keyframes_dir=str(directory))
    with SessionLocal() as db:
        db.add(artifact)
        db.commit()
    return directory


def test_cover_import_save_reload_api_and_prompt_boundaries(caplog):
    client = TestClient(app)
    row = {'aweme_id': AID, 'title': 'Original title', 'cover_url': SIGNED,
           'source_url': f'https://www.douyin.com/video/{AID}?token=secret',
           'desc': 'sessionid=secret', 'media_type': 'video'}
    response = client.post('/api/creator-clone/import', json={'structured_items': json.dumps([row])})
    assert response.status_code == 200
    body = response.json()
    set_id = body['set']['set_id']
    saved = json.loads((settings.creator_clones_dir / set_id / 'samples.json').read_text())
    assert saved['samples'][0]['cover_url'] == SIGNED
    loaded = clone.load_sample_set(set_id)
    assert loaded.samples[0].cover_url == SIGNED
    reread = client.get(f'/api/creator-clone/sets/{set_id}').json()
    assert reread['set']['samples'][0]['cover_url'] == SIGNED
    domain = reread['creator_intelligence']['project']['samples'][0]
    assert domain['cover_url'] == domain['raw']['cover_url'] == SIGNED
    for construct in [clone.build_distill_prompt, clone.build_lite_distill_prompt]:
        prompt = construct(loaded, loaded.samples)
        assert 'abc%2Fxyz' not in prompt and 'image-token' not in prompt
    report = clone.normalize_creator_clone_result({}, loaded, loaded.samples)
    assert 'abc%2Fxyz' not in json.dumps(report)
    assert 'abc%2Fxyz' not in clone.render_creator_clone_markdown(report)
    assert SIGNED not in caplog.text
    assert 'secret' not in reread['set']['samples'][0]['source_url']
    assert 'secret' not in reread['set']['samples'][0]['desc']


def test_browser_handoff_and_profile_cover_keep_exact_query():
    from app.providers.profile_base import ProfileVideoItem
    sample = clone.sample_from_profile_item(ProfileVideoItem(aweme_id=AID, title='Example', cover_url=SIGNED))
    assert sample.cover_url == SIGNED
    browser = _sample_from_browser_item({'aweme_id': AID, 'cover_url': SIGNED})
    assert browser.cover_url == SIGNED
    handoff = _handoff_sample(browser)
    assert handoff['cover_url'] == SIGNED
    assert not clone._handoff_payload_has_sensitive_sample_data({'samples': [handoff]})
    assert clone.sample_from_handoff_item(handoff).cover_url == SIGNED
    assert clone._handoff_payload_has_sensitive_sample_data({'samples': [{'notes': 'sessionid=secret'}]})


@pytest.mark.parametrize('url', [
    'javascript:alert(1)', 'data:image/png;base64,AAAA', '/private/photo.jpg',
    'https://127.0.0.1/a.jpg', 'https://douyinpic.com.evil.test/a.jpg',
    'https://user:pass@p3.douyinpic.com/a.jpg', 'https://p3.douyinpic.com:8443/a.jpg',
    'https://p3.douyinpic.com/a.jpg\n', 'https://p3.douyinpic.com/a.jpg?x=%0a',
    'https://p3.douyinpic.com/../a.jpg', 'https://p3.douyinpic.com/%2e%2e/a.jpg',
    'https://p3.douyinpic.com/api/login', 'https://p3.douyinpic.com/video.mp4',
    'https://p3.douyinpic.com/a.jpg?authorization=Bearer+secret',
    'https://p3.douyinpic.com/a.jpg?cookie=sessionid%3Dsecret',
    'https://p3.douyinpic.com/a.jpg?access_token=secret',
    'https://p3.douyinpic.com/a.jpg?token=sk-abcdefghijklmnop',
    'https://p3.douyinpic.com/a.jpg?' + 'x' * 4096,
    'https://[broken/a.jpg', {}, None,
])
def test_invalid_covers_reject_whole_value_without_breaking_sample(url):
    assert validated_cover_url(url) == ''
    assert clone.sample_from_dict({'sample_id': 'valid', 'cover_url': url}).cover_url == ''


def test_old_cover_is_not_repaired_or_given_other_signature():
    old = SIGNED.split('?')[0]
    assert clone.sample_from_dict({'cover_url': old}).cover_url == old
    assert clone._safe_public_metadata_url(SIGNED) == SIGNED.split('?')[0]
    assert clone._safe_handoff_object({'url': 'https://example.test/a?token=secret'}) != {'url': 'https://example.test/a?token=secret'}


def test_adapter_raw_cannot_restore_rejected_cover():
    from app.services.creator_intelligence.adapters import sample_from_mapping, sample_from_clone_sample
    invalid = 'https://evil.test/a.jpg'
    mapped = sample_from_mapping({'cover_url': invalid})
    assert mapped.cover_url == mapped.raw['cover_url'] == ''
    mapped = sample_from_clone_sample(clone.CloneSample(sample_id='x', cover_url=invalid))
    assert mapped.cover_url == mapped.raw['cover_url'] == ''


def test_preview_formal_api_binding_and_not_persisted_or_sent_to_model():
    make_case()
    sample = clone.CloneSample(sample_id='sample_'+AID, aweme_id=AID, case_id=CID, has_frames=False, cover_url=SIGNED)
    pool = clone.CloneSampleSet(set_id='clone_'+'b'*32, samples=[sample], selected_sample_ids=[sample.sample_id])
    clone.save_sample_set(pool)
    persisted = json.loads((settings.creator_clones_dir / pool.set_id / 'samples.json').read_text())
    assert 'preview_url' not in persisted['samples'][0]
    client = TestClient(app)
    result = client.get(f'/api/creator-clone/sets/{pool.set_id}').json()
    row = result['set']['samples'][0]
    assert row['preview_url'] == f'/api/cases/{CID}/keyframes/frame_0000_00.00s.jpg'
    assert row['preview_source'] == 'video_frame'
    assert result['creator_intelligence']['project']['samples'][0]['raw']['preview_url'] == row['preview_url']
    response = client.get(row['preview_url'])
    image = Image.open(io.BytesIO(response.content)); image.load()
    assert image.size == (32, 24)
    assert row['cover_url'] == SIGNED
    assert result['set']['selected_sample_ids'] == [sample.sample_id]
    assert 'preview_url' not in clone.sample_to_prompt_payload(sample, include_case_reports=False)


def test_missing_wrong_case_or_forged_preview_not_trusted():
    make_case()
    cases = [clone.CloneSample(sample_id='x', case_id='../'+CID, has_frames=True),
             clone.CloneSample(sample_id='y', case_id='case_'+'f'*32, has_frames=True),
             clone.CloneSample(sample_id='z', case_id=CID, aweme_id='7670484770370882862')]
    attach_frame_previews(cases)
    assert all(not s.preview_url for s in cases)
    forged = clone.sample_from_dict({'case_id': CID, 'preview_url': 'https://evil.test/a.jpg'})
    assert forged.preview_url == ''


def test_symlinks_outside_and_empty_directory_rejected(tmp_path):
    directory = make_case()
    for frame in directory.iterdir(): frame.unlink()
    external = tmp_path / 'elsewhere.jpg'
    Image.new('RGB', (5, 5)).save(external)
    (directory / 'frame_0000.jpg').symlink_to(external)
    sample = clone.CloneSample(sample_id='x', case_id=CID, aweme_id=AID)
    attach_frame_previews([sample]); assert not sample.preview_url
    (directory / 'frame_0000.jpg').unlink()
    directory.rmdir(); directory.symlink_to(tmp_path, target_is_directory=True)
    attach_frame_previews([sample]); assert not sample.preview_url
    with SessionLocal() as db:
        db.get(CaseArtifact, CID).keyframes_dir = str(tmp_path)
        db.commit()
    attach_frame_previews([sample]); assert not sample.preview_url


def test_directory_lookup_bounded():
    directory = make_case()
    for i in range(257): (directory / f'entry{i}').touch()
    sample = clone.CloneSample(sample_id='x', case_id=CID, aweme_id=AID)
    attach_frame_previews([sample])
    assert not sample.preview_url

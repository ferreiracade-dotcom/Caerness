"""Repeatable setup/API policy tests; fake HTTP responses are not gameplay evidence."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.error
from unittest.mock import patch

from engine.db import connect, init_db, DEFAULT_DB_PATH
from engine.local_model import chat_local, runtime_config, _headers, _post_json
from engine.model_gateway import render_packet
from engine.planning_gateway import response_schema
from tools.local_ai import candidates, consent, local_name, assert_local, configure_save, dxdiag_gpus, prepare_ollama


def main():
    payload={'conditions':['Do not spend money','Ask the NPC first'],'detail':{'text':'Remember every condition.'}}
    compact=render_packet('local',1,'npc_decision',payload)
    human=render_packet('chatgpt',1,'npc_decision',payload)
    assert json.loads(compact.split('```json\n')[1].split('```')[0])==payload
    assert json.loads(human.split('```json\n')[1].split('```')[0])==payload
    assert len(compact)<len(human)
    grammar=response_schema(42,{'protocol':'narrative_play_v1','read_tools':[{'name':'person'}],'capabilities':[{'name':'advance_time'}]})
    modes=grammar['properties']['proposal']['anyOf']
    assert set(modes[0]['properties'])=={'mode','text'} and modes[0]['additionalProperties'] is False
    assert modes[1]['properties']['calls']['items']['properties']['tool']['enum']==['person']
    assert modes[2]['properties']['plan']['properties']['steps']['items']['properties']['operation']['enum']==['advance_time']
    assert len(response_schema(42,{'phase':'consequences'})['properties']['proposal']['anyOf'])==1
    review=response_schema(42,{'protocol':'narrative_scope_v1'})
    assert review['properties']['proposal']['properties']['authorized']['type']=='boolean'
    assert not consent('Download?', lambda _: '')
    assert not consent('Download?', lambda _: 'no')
    assert consent('Download?', lambda _: 'YES')
    with patch.dict(os.environ, {'OPENAI_API_KEY':'fake-inherited-key'}):
        assert 'Authorization' not in _headers(local_only=True)
    with patch('engine.local_model._urlopen',side_effect=urllib.error.HTTPError('http://127.0.0.1:11434',500,'sensitive upstream body',{},None)):
        try:_post_json('http://127.0.0.1:11434/v1/chat/completions',{},5,local_only=True)
        except ConnectionError as error:assert 'No API key is required' in str(error) and 'sensitive' not in str(error)
        else:raise AssertionError('Failed inference was not reported')
    assert [m['tag'] for m in candidates({'ram_gib': 8, 'gpus': []})] == ['qwen3.5:4b-q4_K_M']
    choices = candidates({'ram_gib': 32, 'gpus': [{'vram_gib': 12}]})
    assert any(m['tag'] == 'gemma4:12b-it-q4_K_M' for m in choices)
    assert not any(m['tag'] == 'gemma4:26b-a4b-it-q4_K_M' for m in choices)
    assert not candidates({'ram_gib': None, 'gpus': []})
    for tag in ('gemma4:31b-cloud', '-bad', 'model; rm', 'https://host/model?secret'):
        try: local_name(tag)
        except ValueError: pass
        else: raise AssertionError(tag)
    for metadata in ({'remote_host': 'ollama.com'}, {'remote_model': 'hidden-cloud'}):
        try: assert_local(metadata)
        except ValueError: pass
        else: raise AssertionError('Cloud alias accepted')
    with tempfile.TemporaryDirectory() as temp:
        xml = Path(temp) / 'display.xml'
        xml.write_text('<DxDiag><DisplayDevices><DisplayDevice><CardName>AMD</CardName><DedicatedMemory>12,288 MB</DedicatedMemory><SharedMemory>32000 MB</SharedMemory></DisplayDevice></DisplayDevices></DxDiag>')
        assert dxdiag_gpus(xml)[0]['vram_gib'] == 12
    hw = {'ram_gib': 16, 'gpus': [], 'disk_free_gib': 30}
    with patch('tools.local_ai.ensure_ollama', return_value='ollama'), patch('tools.local_ai.installed_models', return_value=[]), patch('tools.local_ai.subprocess.run') as pull:
        try: prepare_ollama(hw, input_fn=lambda prompt: 'NO' if 'Type YES' in prompt else '')
        except ValueError as e: assert 'declined' in str(e)
        else: raise AssertionError('Unapproved download proceeded')
        pull.assert_not_called()
    path=Path(os.environ['CAERNESS_DB_PATH']);shutil.copy2(DEFAULT_DB_PATH,path);init_db()
    with connect() as c:
        from engine.player import set_player
        from engine.narrative_runtime import scene
        owner=c.execute("SELECT id FROM actors WHERE name='Robert Baird'").fetchone()[0]
        set_player(c,owner)
        visible=scene(c)['scene']['present_actors']
        assert any(a['actor_type']=='character' for a in visible), 'Institutions crowded all people out of the situated context'
        assert len(visible)<=12 and all('goals' not in a and 'resources' not in a for a in visible)
        from engine.planning_gateway import start_request
        request=start_request(c,'To Petra Fenn: How have you been?',provider='local',narrative=True)
        packet=json.loads(c.execute('SELECT input_json FROM model_requests WHERE id=?',(request['request_id'],)).fetchone()[0])
        assert any(p.get('identity',{}).get('name')=='Petra Fenn' and 'response_cues' in p for p in packet['participants'])
        assert all('goals' not in p and 'resources' not in p for p in packet['participants'])
        before=c.execute('SELECT COUNT(*) FROM actors').fetchone()[0]
        assets=[tuple(r) for r in c.execute('SELECT actor_id,resource_type,amount FROM resources ORDER BY actor_id,resource_type')]
        relationships=[tuple(r) for r in c.execute('SELECT * FROM relationships ORDER BY actor_a_id,actor_b_id')]
        configure_save(c,'http://127.0.0.1:11434/v1/chat/completions','qwen3.5:9b-q4_K_M')
        c.commit()
        cfg=runtime_config(c);assert cfg['free_local'] and not cfg['remote_model']
        response={'choices':[{'message':{'content':'{"ready":true}'},'finish_reason':'stop'}], 'usage':{'completion_tokens':5}}
        with patch('engine.local_model._post_json', side_effect=[{}, response]) as post:
            chat_local(c,[{'role':'user','content':'Return JSON.'}],require_json=True,response_schema={'type':'object'})
            body=post.call_args.args[1]
            assert body['reasoning_effort']=='none' and body['response_format']['type']=='json_schema'
        with patch('engine.local_model._post_json') as post:
            try: chat_local(c,[{'role':'user','content':'x'*30000}])
            except ValueError as e: assert 'context' in str(e)
            else: raise AssertionError('Would silently truncate player conditions')
            post.assert_not_called()
        with patch('engine.local_model._post_json', side_effect=[{}, {'choices':[{'message':{'content':'{}'},'finish_reason':'length'}]}]):
            try: chat_local(c,[{'role':'user','content':'hello'}])
            except ValueError: pass
            else: raise AssertionError('Incomplete output accepted')
        with patch('engine.local_model._post_json', return_value={'remote_host':'ollama.com'}) as post:
            try: chat_local(c,[{'role':'user','content':'hello'}])
            except ValueError as e: assert 'cloud' in str(e)
            else: raise AssertionError('Cloud alias changed after setup')
            assert post.call_count==1
        configure_save(c,'http://127.0.0.1:1234/v1/chat/completions','gemma4:12b')
        c.commit();assert c.execute('SELECT COUNT(*) FROM actors').fetchone()[0] == before
        assert assets==[tuple(r) for r in c.execute('SELECT actor_id,resource_type,amount FROM resources ORDER BY actor_id,resource_type')]
        assert relationships==[tuple(r) for r in c.execute('SELECT * FROM relationships ORDER BY actor_a_id,actor_b_id')]
    with connect() as c: assert runtime_config(c)['local_model']=='gemma4:12b'
    print('Consent, hardware thresholds, cloud rejection, dedicated VRAM, structured gateway, bounded context, incomplete output, model change/reload PASS (mocked policy tests)')

if __name__=='__main__':main()

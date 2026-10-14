"""Non-secret preferences, explicit consent, account limits and key lifecycle."""
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.error
import warnings
from unittest.mock import patch
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from planning_demo import fixture
from engine import ai_providers as p
from engine.local_model import runtime_config,_headers,_post_json
from tools.choose_ai import choose,hidden_key
from tools.narrative_play import main as launch
from free_cloud_ai_test import catalogs

def main():
    c,ids=fixture()
    secret='hidden-setup-secret'
    with tempfile.TemporaryDirectory() as temp,patch('engine.ai_providers.read_public',side_effect=catalogs):
        with patch.dict(os.environ,{'CAERNESS_FREE_LOCAL':'1','CAERNESS_MODEL_API_KEY':'stale-cloud-key','CAERNESS_MODEL_ENDPOINT':'http://127.0.0.1:11434/v1/chat/completions','OPENAI_API_KEY':'stale-openai-key'}):
            answers=iter(['1','YES','FREE','1'])
            assert choose(c,temp,input_fn=lambda _:next(answers),password_fn=lambda _:secret)=='groq'
            assert 'CAERNESS_FREE_LOCAL' not in os.environ and 'OPENAI_API_KEY' not in os.environ and 'CAERNESS_MODEL_API_KEY' not in os.environ
            assert _headers(provider='groq')['Authorization']=='Bearer '+secret
            prefs=json.loads((Path(temp)/'ai-choice.json').read_text())
            assert prefs=={'provider':'groq','model':'openai/gpt-oss-120b'} and secret not in json.dumps(prefs)
            assert secret not in json.dumps(runtime_config(c))
            answers=iter(['4']);assert choose(c,temp,input_fn=lambda _:next(answers))=='ollama'
            assert not p.key_for('groq')
        with patch('engine.ai_providers.read_public',side_effect=AssertionError('Network before consent')):
            answers=iter(['1','no'])
            try:choose(c,temp,input_fn=lambda _:next(answers));raise AssertionError('Privacy declined')
            except ValueError:pass
            answers=iter(['1','YES','no'])
            try:choose(c,temp,input_fn=lambda _:next(answers));raise AssertionError('Billing not confirmed')
            except ValueError:pass
        p._catalogs.clear();p._keys['groq']=secret
        with patch('engine.ai_providers.date') as mock_date:
            mock_date.today.return_value=date(2026,11,14)
            try:p.discover('groq');raise AssertionError('Expired free model assumptions')
            except p.ProviderError:pass
        p._catalogs.clear()
        with patch('engine.ai_providers.read_public',side_effect=p.ProviderError('Verification unavailable')):
            try:p.discover('openrouter');raise AssertionError('Offline verification bypassed')
            except p.ProviderError:pass
        # Incompatible saved endpoint cannot receive a vault key even on loopback.
        for endpoint in ('http://127.0.0.1:1234/v1/chat/completions','https://example.com/v1/chat/completions'):
            try:_post_json(endpoint,{},5,provider='groq');raise AssertionError('Wrong credential destination')
            except p.ProviderError:pass
        try:p.validate({'device_profile':'desktop_free_cloud_groq','local_endpoint':'http://127.0.0.1:1234/v1/chat/completions','local_model':'openai/gpt-oss-120b'});raise AssertionError('Credential endpoint swap')
        except p.ProviderError:pass
        with patch('getpass.getpass',side_effect=__import__('getpass').GetPassWarning('would echo')):
            try:hidden_key('Key:');raise AssertionError('Insecure input fallback')
            except ValueError:pass
        # Exercise the actual launcher controller, not only the setup helper.
        # The response is explicitly mocked; no provider access is claimed.
        from engine.local_model import LocalModelResult
        answers=iter(['1','YES','FREE','1'])
        campaign=Path(temp)/'launcher-campaign.db'
        with patch.object(sys,'argv',['narrative_play','--choose-ai','--probe','--save',str(campaign)]),patch('tools.choose_ai.choose',side_effect=lambda conn,folder:choose(conn,folder,input_fn=lambda _:next(answers),password_fn=lambda _:secret)),patch('engine.local_model.chat_local',return_value=LocalModelResult('{"ready":true,"reply":"[MOCK] Hello"}','mock','explicit-mock',55,18,latency_seconds=.01)):
            launch()
        assert campaign.exists()
        diagnostic=json.loads((Path(temp)/'cloud-inference-check.json').read_text())
        assert diagnostic['provider']=='groq' and secret not in json.dumps(diagnostic)
        assert p.key_for('groq')==secret
    p.clear_keys();p._catalogs.clear();c.close()
    print('Setup privacy/billing consent, stale-env clearing, hidden keys, provider/local switching, expiring free review and offline fail-closed PASS (no inference)')
if __name__=='__main__':main()

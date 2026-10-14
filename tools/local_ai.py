"""Local-only setup policy and Windows hardware discovery; no game operations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET

GIB = 1024 ** 3
OLLAMA = 'http://127.0.0.1:11434'
# Conservative download ceilings, not measured inference memory or quality scores.
# Explicit GGUF Q4_K_M tags avoid changing default backends/quantizations.
MODELS = (
    {'tag': 'qwen3.5:4b-q4_K_M', 'gb': 3.5, 'ram': 8, 'vram': 5, 'label': 'Diagnostic fallback: gameplay quality not yet accepted'},
    {'tag': 'qwen3.5:9b-q4_K_M', 'gb': 7, 'ram': 16, 'vram': 9, 'label': 'First gameplay candidate; compare prose before accepting'},
    {'tag': 'gemma4:12b-it-q4_K_M', 'gb': 9, 'ram': 24, 'vram': 12, 'label': 'Alternative gameplay candidate; compare with Qwen'},
    {'tag': 'gemma4:26b-a4b-it-q4_K_M', 'gb': 18, 'ram': 48, 'vram': 24, 'label': 'Larger comparison candidate, not automatically better'},
    {'tag': 'qwen3.5:27b-q4_K_M', 'gb': 19, 'ram': 48, 'vram': 24, 'label': 'Larger dense comparison candidate'},
)


def command(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=timeout).stdout


def dxdiag_gpus(path):
    result = []
    for device in ET.parse(path).findall('.//DisplayDevice'):
        value = device.findtext('DedicatedMemory', '')
        match = re.search(r'([\d,]+)\s*MB', value, re.I)
        result.append({'name': device.findtext('CardName', 'Unknown GPU'),
                       'vram_gib': int(match[1].replace(',', '')) / 1024 if match else None,
                       'source': 'dxdiag dedicated memory'})
    return result


def hardware():
    model_disk = Path(os.environ.get('OLLAMA_MODELS', str(Path.home() / '.ollama' / 'models'))).expanduser()
    while not model_disk.exists():
        model_disk = model_disk.parent
    result = {'system': platform.system(), 'ram_gib': None, 'gpus': [], 'cpu_count': os.cpu_count(),
              'disk_free_gib': shutil.disk_usage(model_disk).free / GIB, 'model_disk': str(model_disk), 'warnings': []}
    if platform.system() == 'Windows':
        try:
            result['ram_gib'] = int(command(['powershell', '-NoProfile', '-Command',
                '(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory']).strip()) / GIB
        except (OSError, ValueError, subprocess.SubprocessError):
            result['warnings'].append('RAM could not be measured; no automatic download recommendation.')
    else:
        try:
            result['ram_gib'] = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / GIB
            cap = Path('/sys/fs/cgroup/memory.max')
            if cap.exists() and cap.read_text().strip().isdigit():
                result['ram_gib'] = min(result['ram_gib'], int(cap.read_text()) / GIB)
        except (OSError, ValueError):
            result['warnings'].append('RAM could not be measured.')
    try:
        rows = command(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'])
        for line in rows.splitlines():
            name, mib, driver = line.rsplit(',', 2)
            result['gpus'].append({'name': name.strip(), 'vram_gib': float(mib) / 1024, 'driver_version':driver.strip(), 'source': 'nvidia-smi'})
    except (OSError, ValueError, subprocess.SubprocessError):
        if platform.system() == 'Windows':
            try:
                with tempfile.TemporaryDirectory(prefix='caerness-hardware-') as folder:
                    report = Path(folder) / 'display.xml'
                    command(['dxdiag', '/dontskip', '/x', str(report)], timeout=45)
                    result['gpus'] = dxdiag_gpus(report)
            except (OSError, ET.ParseError, subprocess.SubprocessError):
                result['warnings'].append('GPU/VRAM unavailable. Shared graphics memory is never counted as dedicated VRAM.')
    return result


def candidates(hw):
    # Do not pool VRAM across cards. Leave room for OS, Python and an 8K KV cache.
    ram = hw.get('ram_gib') or 0
    # Partial offload/CPU remain possible when RAM fits; explain the speed tradeoff.
    return [m for m in MODELS if ram >= m['ram'] - .5]  # firmware reservations on nominal 8/16/24 GB systems


def process_memory():
    """Observed runtime RSS/peak RSS, not a guaranteed model memory requirement."""
    if platform.system() == 'Windows':
        try:
            result=json.loads(command(['powershell','-NoProfile','-Command',
                'Get-Process -Name ollama,llama-server -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,WorkingSet64,PeakWorkingSet64 | ConvertTo-Json']))
            return result if isinstance(result,list) else [result]
        except (OSError,ValueError,subprocess.SubprocessError):return []
    result=[]
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            name=Path(p.read_bytes().split(b'\0')[0].decode()).name
            if name not in {'ollama','llama-server'}:continue
            status=(p.parent/'status').read_text()
            fields={k: int(v) * 1024 for k,v in re.findall(r'^(VmRSS|VmHWM):\s+(\d+) kB',status,re.M)}
            result.append({'pid':int(p.parent.name),'name':name,**fields})
        except (OSError,ValueError):continue
    return result


def ollama_performance_probe(model):
    """Small native timing diagnostic; gameplay continues through the OpenAI gateway."""
    begin=time.perf_counter()
    result=api('/api/chat',{'model':local_name(model),'stream':False,'think':False,
        'messages':[{'role':'user','content':'Return a JSON object with ready set to true. This is a diagnostic, not gameplay.'}],
        'format':{'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready'],'additionalProperties':False},
        'options':{'num_ctx':8192,'num_predict':60}},timeout=300)
    if json.loads(result['message']['content'])!={'ready':True}:raise ValueError('Native performance diagnostic failed.')
    output={k:result.get(k) for k in ('total_duration','load_duration','prompt_eval_count','prompt_eval_duration','eval_count','eval_duration')}
    output.update({'duration_unit':'nanoseconds','wall_seconds':round(time.perf_counter()-begin,4),
        'generation_tokens_per_second':result['eval_count'] * 1e9 / result['eval_duration'] if result.get('eval_duration') else None,
        'runtime_process_memory':process_memory(),'gameplay_acceptance':'NOT_TESTED'})
    return output


def local_name(name):
    if not re.fullmatch(r'[A-Za-z0-9_./:-]+', name) or 'cloud' in name.lower() or name.startswith('-'):
        raise ValueError('Choose a local model name; cloud tags and command options are not permitted.')
    return name


def api(path, payload=None, timeout=20):
    from engine.local_model import _urlopen
    request = urllib.request.Request(OLLAMA + path, headers={'Content-Type': 'application/json'},
        data=json.dumps(payload).encode() if payload is not None else None)
    with _urlopen(request, timeout) as response:
        return json.load(response)


def assert_local(info):
    if info.get('remote_model') or info.get('remote_host'):
        raise ValueError('This installed alias uses cloud inference. Select a genuinely local model.')
    return info


def installed_models():
    return api('/api/tags').get('models', [])


def consent(prompt, input_fn=input):
    return input_fn(prompt + ' Type YES to agree: ').strip().upper() == 'YES'


def find_ollama():
    found = shutil.which('ollama')
    if found:
        return found
    candidate = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/ollama.exe'
    return str(candidate) if candidate.is_file() else None


def ensure_ollama():
    exe = find_ollama()
    if not exe:
        print('Ollama is missing. The official Windows installer is free (roughly 4 GB of installed software).')
        if not consent('Open the official installer page? No model will be downloaded yet.'):
            raise ValueError('Installation declined. You can instead use LM Studio.')
        import webbrowser
        webbrowser.open('https://ollama.com/download/windows')
        input('Install Ollama, then press Enter here to continue: ')
        exe = find_ollama()
        if not exe:
            raise ValueError('Ollama was not found after installation. Restart this launcher after installing it.')
    try:
        api('/api/version', timeout=2)
    except (OSError, ValueError):
        env = dict(os.environ, OLLAMA_NO_CLOUD='1', OLLAMA_HOST='127.0.0.1:11434', OLLAMA_NUM_PARALLEL='1')
        # Prefer the supported NVIDIA CUDA path on Windows; do not retry a known
        # unstable Vulkan backend. Explicit user settings still take precedence.
        if platform.system()=='Windows' and any('nvidia' in g['name'].lower() or g.get('source')=='nvidia-smi' for g in hardware()['gpus']):
            env.setdefault('OLLAMA_VULKAN','0')
        subprocess.Popen([exe, 'serve'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            try:
                api('/api/version', timeout=1)
                break
            except (OSError, ValueError):
                time.sleep(.5)
        else:
            raise ValueError('Ollama did not start. Open Ollama from the Windows Start menu, then try again.')
    return exe


def prepare_ollama(hw, preferred=None, change=False, input_fn=input):
    exe = ensure_ollama()
    if preferred and not change:
        try:
            info = assert_local(api('/api/show', {'model': local_name(preferred)}))
            return preferred, info
        except OSError:
            print('The saved model is not installed. Choose one below.')
    choices = candidates(hw)
    known = installed_models()
    print('\nHardware-sized download candidates (not a literary-quality ranking):')
    for i, m in enumerate(choices, 1):
        vram = max((g.get('vram_gib') or 0 for g in hw['gpus']), default=0)
        acceleration = 'GPU memory candidate; verify actual loading' if vram >= m['vram'] else 'GPU fit uncertain; CPU/partial offload may take minutes'
        print(f" {i}. {m['tag']} — up to {m['gb']} GB; {m['label']}; {acceleration}")
    print('Installed models:', ', '.join(m['name'] for m in known) or 'none')
    if not choices:
        raise ValueError('No safe automatic recommendation for this hardware. Use LM Studio to inspect hardware, or upgrade memory.')
    vram=max((g.get('vram_gib') or 0 for g in hw['gpus']),default=0)
    accelerated=[m for m in choices if vram>=m['vram']]
    recommended=next((m for m in accelerated if m['tag'].startswith('qwen3.5:9b')),accelerated[0] if accelerated else choices[0])
    if not accelerated:
        print('No candidate fits entirely within detected VRAM. Start with the smallest model; RAM capacity alone does not make 9B responsive. CPU/partial offload remains an unaccepted speed/quality compromise.')
    selection = input_fn(f"Model number or installed local name [{recommended['tag']}]: ").strip() or recommended['tag']
    if selection.isdigit():
        index = int(selection) - 1
        if not 0 <= index < len(choices):
            raise ValueError('That model number is not in the displayed list.')
        selection = choices[index]['tag']
    selection = local_name(selection)
    if selection not in {m['name'] for m in known}:
        entry = next((m for m in choices if m['tag'] == selection), None)
        if not entry:
            raise ValueError('For a new download, choose a displayed hardware-sized candidate. Other models can be installed in LM Studio/Ollama first.')
        if hw['disk_free_gib'] < entry['gb'] + 3:
            raise ValueError('Insufficient free disk space for this download plus working room.')
        if not consent(f"Download {selection}, up to {entry['gb']} GB, to this computer? No subscription or token charge.", input_fn):
            raise ValueError('Download declined. Your campaign is unchanged.')
        subprocess.run([exe, 'pull', selection], check=True)
    info = assert_local(api('/api/show', {'model': selection}))
    # Alias references existing weight blobs; bounded context prevents allocating 128K/256K.
    alias = 'caerness-' + re.sub(r'[^A-Za-z0-9_-]', '-', selection)
    api('/api/create', {'model': alias, 'from': selection, 'parameters': {'num_ctx': 8192}, 'stream': False}, timeout=180)
    return alias, assert_local(api('/api/show', {'model': alias}))


def configure_save(conn, endpoint, model):
    from engine.local_model import set_runtime_config,runtime_config
    from urllib.parse import urlsplit
    if urlsplit(endpoint).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Free local setup requires a loopback endpoint.')
    local_name(model)
    prior=runtime_config(conn)
    budgets={k:prior[k] for k in ('local_max_context_tokens','local_heavy_context_tokens','local_max_output_tokens')} if prior.get('free_local') and prior['local_model']==model and prior['local_endpoint']==endpoint else {'local_max_context_tokens':6000,'local_heavy_context_tokens':8192,'local_max_output_tokens':1200}
    return set_runtime_config(conn, device_profile='desktop_free_local', local_backend='openai_compatible',
        local_endpoint=endpoint, local_model=model, local_timeout_seconds=300,
        **budgets,
        referral_for_quality=0, referral_for_reasoning=0, referral_for_hardware=0)


def inference_probe(conn, *, max_tokens=120):
    from engine.local_model import chat_local
    schema = {'type': 'object', 'properties': {'ready': {'type': 'boolean'}, 'reply': {'type': 'string'}},
              'required': ['ready', 'reply'], 'additionalProperties': False}
    result = chat_local(conn, [
        {'role': 'system', 'content': 'Return JSON matching the requested schema. No reasoning text. This is a connection diagnostic, not gameplay.'},
        {'role': 'user', 'content': 'Set ready to true and reply to a short greeting in plain English.'}],
        max_tokens=max_tokens, require_json=True, response_schema=schema)
    parsed = json.loads(result.text)
    if set(parsed) != {'ready', 'reply'} or parsed['ready'] is not True or not isinstance(parsed['reply'], str) or not parsed['reply'].strip():
        raise ValueError('Model inference did not satisfy the structured diagnostic. No successful gameplay is claimed.')
    return {'status': 'REAL_INFERENCE_DIAGNOSTIC_PASSED', 'model': result.model,
            'latency_seconds': result.latency_seconds, 'prompt_tokens': result.prompt_tokens,
            'completion_tokens': result.completion_tokens,
            'output_tokens_per_wall_second': result.completion_tokens / result.latency_seconds if result.completion_tokens and result.latency_seconds else None,
            'response': parsed, 'gameplay_acceptance': 'NOT_TESTED'}

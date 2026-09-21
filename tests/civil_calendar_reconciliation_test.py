from __future__ import annotations
import json, hashlib, os, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
os.environ['CAERNESS_TEST_MODE']='1'

from engine.civil_calendar import sv_date_from_day, day_from_sv_date, format_sv_date, MONTH_LENGTHS
from engine.current_seed import DEFAULT_CURRENT_SEED
from engine.bootstrap import DEFAULT_SEED, load_seed


def run():
    assert sum(MONTH_LENGTHS)==365
    assert sv_date_from_day(0)==(624,1,1)
    assert sv_date_from_day(364)==(624,12,31)
    assert sv_date_from_day(-1)==(623,12,31)
    assert day_from_sv_date(624,1,1)==0
    assert day_from_sv_date(623,12,31)==-1
    for x in (-100000,-53531,-48371,-365,-1,0,30,31,364,365,99999):
        y,m,d=sv_date_from_day(x)
        assert day_from_sv_date(y,m,d)==x
    assert format_sv_date(-53531)=='3 Fifth Month, 477 SV'
    assert format_sv_date(-26156)=='3 Fifth Month, 552 SV'
    assert format_sv_date(-48371)=='23 Sixth Month, 491 SV'
    assert format_sv_date(-23551)=='23 Sixth Month, 559 SV'

    canon_hash=hashlib.sha256((ROOT/'canon'/'world_bible_current.docx').read_bytes()).hexdigest()
    current=json.loads(DEFAULT_CURRENT_SEED.read_text(encoding='utf-8'))
    assert current['meta']['world_bible_sha256']==canon_hash
    assert not any(q.get('id')=='open:calendar' for q in current['protected_open_questions'])
    assert current['meta']['civil_calendar']['opening_date']=='1 First Month, 624 SV'
    for p in current['persons']:
        assert p['birth_date_sv']==format_sv_date(p['birth_day'])
        if isinstance(p.get('death_day'),int):
            assert p['death_date_sv']==format_sv_date(p['death_day'])

    core=load_seed(DEFAULT_SEED)
    assert core['seed_version']==3
    assert core['world_bible_sha256']==canon_hash
    print('civil calendar/canon reconciliation PASS')

if __name__=='__main__': run()

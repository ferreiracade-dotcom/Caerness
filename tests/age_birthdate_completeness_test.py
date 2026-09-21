from __future__ import annotations
import json, os, sys, tempfile, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
os.environ['CAERNESS_TEST_MODE']='1'

from engine.db import connect, init_db, reset_db
from engine.current_seed import import_current_seed, DEFAULT_CURRENT_SEED
from engine.bootstrap import load_seed, DEFAULT_SEED
from engine.civil_calendar import format_sv_date, day_from_sv_date

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def docx_text(path:Path)->str:
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read('word/document.xml'))
    out=[]
    for node in root.iter():
        if node.tag==W+'t' and node.text: out.append(node.text)
        elif node.tag in {W+'br',W+'cr'}: out.append('\n')
    return ''.join(out)

def run():
    seed=json.loads(DEFAULT_CURRENT_SEED.read_text(encoding='utf-8'))
    people=seed['persons']
    assert len(people)==464
    assert all(isinstance(p.get('age'),int) and p['age']>=0 for p in people)
    assert all(isinstance(p.get('birth_day'),int) for p in people)
    assert all(p.get('birth_date_sv')==format_sv_date(p['birth_day']) for p in people)
    living=[p for p in people if p.get('life_status')=='living']
    historical=[p for p in people if p.get('life_status')!='living']
    assert len(historical)==2
    for p in living:
        assert (-p['birth_day'])//365==p['age'],p
    for p in historical:
        assert isinstance(p.get('death_day'),int),p
        assert p.get('death_date_sv')==format_sv_date(p['death_day']),p
        assert (p['death_day']-p['birth_day'])//365==p['age'],p

    repaired={p['name']:p['age'] for p in people if p.get('registry_age_basis')}
    expected={
        'Maurice Penn':55,'Brock Ames':41,'Vaughn Hester':48,'Clive Orton':36,'Tucker Hewitt':44,
        'Nadine Croft':30,'Eli Hobb':34,'Joyce Rudd':21,'Beatrice Snow':57,'Alaric Boone':45,
        'Dominic Pryce':52,'Damon Flint':49,'Hadrian Bellgrave':65,'Wilfred Penrose':71,'Alban Fairwick':58,
        'Marius Ashcombe':64,'Thaddeus Ormond':61,'Rolfe Durn':74,'Bishop Dario Pellin':59,
        'Aurelia Morn':68,'Corvin Latch':75,
    }
    assert repaired==expected,(repaired,expected)

    # World Bible must no longer describe age as open/light and must carry the complete ledger.
    text=docx_text(ROOT/'canon'/'world_bible_current.docx')
    lowered=text.lower()
    for stale in ['age open','age/stage not locked','their ages and deeper biographies remain deliberately light','their ages and deeper biographies remain light until']:
        assert stale not in lowered,stale
    assert 'Named-person age and birth-date ledger' in text
    assert 'Registry completeness rule.' in text
    assert '1 First Month, 624 SV' in text
    assert 'calendar has not been fixed' not in lowered
    assert day_from_sv_date(624,1,1)==0
    assert format_sv_date(-53531)=='3 Fifth Month, 477 SV'
    assert format_sv_date(-26156)=='3 Fifth Month, 552 SV'
    assert format_sv_date(-48371)=='23 Sixth Month, 491 SV'
    assert format_sv_date(-23551)=='23 Sixth Month, 559 SV'
    for name,age in expected.items():
        assert name in text,(name,'missing from World Bible')

    # Fresh current-canon import persists exact chronology for every named person.
    reset_db(force=True,backup=False); init_db()
    with connect() as c:
        result=import_current_seed(c)
        assert result['persons']==464,result
        missing=c.execute("""SELECT COUNT(*) FROM source_identity_map m
                              JOIN actors a ON a.id=m.entity_id AND m.entity_kind='actor'
                              LEFT JOIN actor_life_profiles l ON l.actor_id=a.id
                              WHERE m.source_namespace='caerness_seed_v1_1' AND m.source_key LIKE 'person:%'
                                AND l.birth_day IS NULL""").fetchone()[0]
        assert missing==0,missing
        for name,age in expected.items():
            row=c.execute("""SELECT l.birth_day,l.life_status FROM actors a JOIN actor_life_profiles l ON l.actor_id=a.id WHERE a.name=?""",(name,)).fetchone()
            assert row is not None,name
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()

    # Legacy/alternate campaign bootstrap also requires explicit dates and hashes against repaired canon.
    core=load_seed(DEFAULT_SEED)
    assert int(core['seed_version'])==3
    assert core['world_bible_sha256']==__import__('hashlib').sha256((ROOT/'canon'/'world_bible_current.docx').read_bytes()).hexdigest()
    assert all(x.get('birth_date_sv')==format_sv_date(x['birth_day']) for x in core['named_characters'])
    assert all(isinstance(x.get('birth_day'),int) for x in core['named_characters'])
    print('age/birthdate completeness PASS')

if __name__=='__main__': run()

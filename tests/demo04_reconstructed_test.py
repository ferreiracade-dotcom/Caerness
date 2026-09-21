from __future__ import annotations
import os
os.environ['CAERNESS_TEST_MODE']='1'
os.environ['CAERNESS_DB_PATH']='/tmp/caerness_demo04_reconstructed.db'
from engine.db import reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.background_population import process_due_population_life_course,current_world_population


def fresh():
    reset_db(force=True,backup=False);init_db();c=connect();import_current_seed(c);activate_existing_loops(c);c.commit();return c

def run():
    c=fresh()
    try:
        opening=current_world_population(c); assert opening==52_000_000,opening
        r=process_due_population_life_course(c,365)
        closing=current_world_population(c)
        assert round(float(r['births']))==1_404_000,r
        assert round(float(r['deaths']))==1_286_220,r
        assert closing==52_117_780,(closing,r)
    finally:c.close()
    c=fresh()
    try:
        for y in range(1,11): process_due_population_life_course(c,365*y)
        closing10=current_world_population(c)
        assert abs(closing10-53_470_526)<=1,closing10
        print('DEMO-04 reconstructed PASS',{'opening':52_000_000,'births_y1':1_404_000,'deaths_y1':1_286_220,'closing_y1':52_117_780,'closing_y10':closing10})
    finally:c.close()
if __name__=='__main__':run()

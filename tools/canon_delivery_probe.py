"""Measure which World Bible passages the narrator's canon search actually delivers.

Builds many plausible scene queries the same way engine/player.py:_canon_query does (place, protagonist,
request, up to four present people), runs the engine's own canon search, and reports how the 6 slots per
scene are spent, by Part and for sections that every scene should be able to draw on.

Since SCENE-01 step 1 the narrator also receives a fixed scene brief (reading lenses + culture briefs) and its
search excludes engine-only and open Parts; the probe measures both. --baseline reproduces the old search.

Usage: python tools/canon_delivery_probe.py COPY.db [--scenes 400] [--seed 7] [--baseline] [--out hits.json]
Run it on a COPY: it indexes the World Bible into the database if it is not indexed yet.
"""
import argparse, collections, json, os, random, sqlite3, sys

ap = argparse.ArgumentParser()
ap.add_argument("db"); ap.add_argument("--scenes", type=int, default=400); ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--out"); ap.add_argument("--baseline", action="store_true", help="old search: no brief, no exclusion")
args = ap.parse_args()
os.environ["CAERNESS_DB_PATH"] = os.path.abspath(args.db)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.canon import DEFAULT_CANON, _search_canon_with_conn, index_canon  # noqa: E402
from engine.scene_brief import NARRATOR_EXCLUDED_PARTS, build_scene_brief  # noqa: E402

conn = sqlite3.connect(args.db); conn.row_factory = sqlite3.Row
if not conn.execute("SELECT COUNT(*) FROM canon_chunks").fetchone()[0]:
    conn.close(); index_canon(DEFAULT_CANON)
    conn = sqlite3.connect(args.db); conn.row_factory = sqlite3.Row

# Sections a scene should be able to draw on whenever their situation arises (World Bible Parts 0, 2, 3, 21-23).
WATCH = ["two lenses", "Recognition and social presence", "Formality, familiarity", "same bow", "Power, authority",
         "Culture is not alignment", "Dress and visible status", "Regional variation", "Outsiders and acculturation",
         "Death in a martial", "Ancestors, mourning", "Challenge culture", "Masters, teachers", "Clothing, repair",
         "Food and ordinary", "Regional social expressions", "Underworld justice", "Reputation is a social system",
         "Gossip, intelligence", "> Presence", "Naming grammar"]
REQUESTS = ["", "I walk into the inn and look for a table", "I walk down the main road through the market",
            "I greet the clan head", "I ask the merchant what he wants for the horse", "I go to see my master",
            "I report to my captain", "I sit by the fire and talk with the prisoner", "I visit the temple",
            "I enter the governor's hall", "I meet my men in the yard", "I buy new clothes", "I challenge him to a duel",
            "I collect the protection money", "I ride out with my escort"]

rng = random.Random(args.seed)
locs = conn.execute("""SELECT l.id,l.name,l.kind FROM locations l WHERE EXISTS(SELECT 1 FROM actors a
    WHERE a.current_location_id=l.id AND a.actor_type='character' AND a.status='active')""").fetchall()
hits = collections.Counter(); brief_cultures = collections.Counter(); briefed = 0
exclude = () if args.baseline else NARRATOR_EXCLUDED_PARTS
for _ in range(args.scenes):
    loc = rng.choice(locs)
    people = conn.execute("SELECT name,subtype FROM actors WHERE current_location_id=? AND actor_type='character' "
                          "AND status='active'", (loc["id"],)).fetchall()
    me = rng.choice(people)
    terms = ["Caerness", loc["name"] or "", loc["kind"] or "", me["name"], me["subtype"] or "", rng.choice(REQUESTS)]
    terms += [p["name"] for p in rng.sample(people, min(4, len(people)))]
    for ch in _search_canon_with_conn(conn, " ".join(t for t in terms if t), 6, exclude):
        hits[ch.heading_path] += 1
    if not args.baseline:
        ids = [r["id"] for r in conn.execute("SELECT id FROM actors WHERE current_location_id=? AND actor_type='character' "
                                               "AND status='active'", (loc["id"],))][:4]
        brief = build_scene_brief(conn, loc["id"], ids)
        briefed += bool(brief["reading_lenses"]["text"])
        for c in brief["cultures"]:
            brief_cultures[f"{c['culture']} ({c['applies']})"] += 1

headings = [r[0] for r in conn.execute("SELECT heading_path FROM canon_chunks")]
part = lambda h: h.split(" > ")[0]
total, used = collections.Counter(map(part, headings)), collections.Counter()
for h, n in hits.items():
    used[part(h)] += n
slots = args.scenes * 6
print(f"{args.scenes} scenes, {slots} slots; {len(hits)} of {len(set(headings))} sections ever delivered")
for p in sorted(total, key=lambda p: -used[p]):
    print(f"  {used[p]:5d} ({100 * used[p] / slots:4.1f}%)  {total[p]:3d} chunks  {p[:72]}")
if not args.baseline:
    print(f"scene brief: reading lenses in {briefed} of {args.scenes} scenes; culture briefs delivered:")
    for k, n in brief_cultures.most_common():
        print(f"  {n:4d}  {k}")
print("watched sections (times delivered by search):")
for k in WATCH:
    print(f"  {sum(n for h, n in hits.items() if k in h):4d}  {k}")
if args.out:
    json.dump({"scenes": args.scenes, "hits": hits}, open(args.out, "w"), indent=1)

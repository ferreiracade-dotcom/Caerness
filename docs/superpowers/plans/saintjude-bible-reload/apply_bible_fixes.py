"""Apply the bible corrections (REPORT.md section 3, problems 1-27) to the seven source files in bible_v2/.
Each edit must match exactly once. Then: python tools/build_saintjude_bible.py <this>/bible_v2"""
import sys
from pathlib import Path
D = Path(__file__).resolve().parent / "bible_v2"
F = {"idx": "Saint_Jude_Bible_Index.md", "I": "Saint_Jude_Bible_Part_I_The_City.md", "II": "Saint_Jude_Bible_Part_II_The_Law.md",
     "III": "Saint_Jude_Bible_Part_III_The_Underworld.md", "IV": "Saint_Jude_Bible_Part_IV_The_Upperworld.md",
     "V": "Saint_Jude_Bible_Part_V_The_Outside_Groups.md", "VI": "Saint_Jude_Bible_Part_VI_The_Price_Book.md"}
T = {k: (D / v).read_text(encoding="utf-8") for k, v in F.items()}
bad = []
def rep(part, old, new):
    n = T[part].count(old)
    if n != 1:
        bad.append((part, n, old[:90]))
        return
    T[part] = T[part].replace(old, new)

TOWNS = ("Highlands, Atlantic Highlands, Middletown, Keansburg, Hazlet, Union Beach, Keyport, Aberdeen and Matawan on the bayshore; "
 "Sea Bright, Monmouth Beach, Long Branch, West Long Branch, Oceanport, Eatontown, Deal, Allenhurst, Loch Arbour, Asbury Park, Ocean Township, Neptune, Neptune City, Bradley Beach, Avon-by-the-Sea and Belmar on the shore; "
 "Red Bank, Little Silver, Fair Haven, Rumson, Shrewsbury, Tinton Falls, Interlaken and Holmdel along the river and inland; "
 "Freehold, Marlboro, Colts Neck, Manalapan and Englishtown in the inner Monmouth country; and Old Bridge, Sayreville and South Amboy in Middlesex")

# ---- Part I
rep("I", "- **Pine County** (west): the Pines and the outer exurbs.", "- **Pine County** (south-west): the Pines and the outer exurbs.")
rep("I", "**the Pines** (west, thirty miles)", "**the Pines** (south-west, thirty miles)")
rep("I", "Thirty miles west in Pine County", "Thirty miles south-west in Pine County")
rep("I", "State daily numbers game (Pick-3, 22 May 1975)", "State daily numbers game (Pick-it, 22 May 1975; Pick-3 from 1987)")
rep("I", "The State's daily three-digit game, **Pick-3**, begins on 22 May 1975", "The State's daily three-digit game, **Pick-it** (renamed Pick-3 in 1987), begins on 22 May 1975")
rep("I", "the State Commission of Investigation (1969)", "the State Commission of Investigation (created 1968, working from 1 January 1969)")
rep("I", "**Monsignor Boyle's** rectory", "the cathedral rectory")
rep("I", "### 5.8 District Eight: The Heights and Oakridge (the Gold Coast)",
    "### 5.8 District Eight: The Heights (the Gold Coast)\n\n**Oakridge** lies outside the city line, in Marsh County (3.1a, 4.1). It is described here because the Heights' money, clubs and families reach into it.")
rep("I", "the **Metropolitan Correctional Center** (fourteen stories", "the **federal detention center** (name **Open**; fourteen stories")
rep("I", "The Federal MCC opens downtown", "The federal detention center opens downtown")
rep("I", "| Mixed, other | about 8% | Everywhere |", "| Soviet Jewish émigrés | about 0.2% | Brighton Point |\n| Mixed, other | about 7.8% | Everywhere |")
rep("I", "**The old codex timeline's \"1982 Barber Shop Hit,\" later \"1977,\" is no longer history.** If it happens, it happens in the simulation.\n\n", "")
rep("I", "See the Economy of Face in Part III.", "See Part III 2, Courtesy and Ceremony.")
rep("I", "- **Fenwick (College Hill).** The university district.", "- **Fenwick (College Hill).** The university district, on the north bank west of Crown Harbor, between Bellacorte and Greenwood.")
rep("I", "A dozen blocks of Chinese restaurants and laundries", "On the north bank behind the North Piers, a dozen blocks of Chinese restaurants and laundries")
rep("I", "The metropolitan total is Open; the suburbs take most of those who leave the city.",
    "The 1975 metropolitan total of 2.4 million is Fixed. Only its later path is Open, and the suburbs take most of those who leave the city.")
rep("I", "still falling (Weather: the decline continues through the decade).",
    "still falling (Weather: the decline continues through the decade).\n\n**Design (outside the city).** The metropolitan area outside the city, about 1.3 million people in 1975, is not split by county in this bible. The engine holds it as one suburban remainder, and its birth, infant-death and age figures follow the 1975 United States rates until a revision of this Part sets them.")
rep("I", "The real towns there (Long Branch, Asbury Park, Red Bank and their neighbors) do not exist, and the Storyteller may borrow their names for neighborhoods.",
    "The real towns there do not exist: " + TOWNS + ". The Storyteller may borrow their names for neighborhoods. Real places beyond that ground, such as Perth Amboy, New Brunswick, Edison and Wall, exist as they are.")

# ---- Part III
rep("III", "| Sabatini | 50 to 60 | 5 to 8 |", "| Sabatini | 50 to 60, default 57 | 5 to 8 |")
rep("III", "| Ferrante | 40 to 50 | 6 to 8 |", "| Ferrante | 40 to 50, default 44 | 6 to 8 |")
rep("III", "| Vannucci | 30 to 40 | 5 to 7 |", "| Vannucci | 30 to 40, default 36 | 5 to 7 |")
rep("III", "A family's strength is not its head count alone.",
    "The defaults in the table are the peaks of the engine's draw and sum to 182, inside 180 to 190. Part VI's scale test uses the range midpoints (55, 45, 45 and 35, which sum to 180). A family's strength is not its head count alone.")
rep("III", "**A note on scale (a decision for Cade).**", "**A note on scale.**")
rep("III", "kept **10 percent** of the play, and the runner's share is **10 percent** of the play [verified", "kept **10 percent** of the play [verified")
rep("III", "the gun shows and the Armorer.**", "the gun shows and the armorer, an **Open** role: whoever supplies a family's guns, invented when needed.**")
rep("III", "the Master Layoff bank, restaurants and nightclubs downtown", "the Master Layoff bank (kept in Crown Harbor), restaurants and nightclubs downtown")
rep("III", "a car-crushing yard, wholesale gambling", "a car-crushing yard in the Eastside rail yards, wholesale gambling")

# ---- Part VI
rep("VI", "| Legitimate fronts | 5.0 (2.1 to 8.4) | 2.5 (1.0 to 4.0) | 0.5 (0.2 to 1.0) | 0.8 (0.3 to 1.4) | 1.2 (0.6 to 2.0) | | 4.5 |",
    "| Legitimate fronts | 5.0 (2.1 to 8.4) | 50 | 10 | 16 | 24 | Family ranges, $M: Sabatini 1.0 to 4.0, Pellegrino 0.2 to 1.0, Vannucci 0.3 to 1.4, Ferrante 0.6 to 2.0 | 4.5 |")
rep("VI", "| Drugs (by dial and ground) | 0.54 (0.27 to 1.08) | 0.14 | 0.03 | 0.19 | 0.18 | Range half to double, *new* | 6.5 |",
    "| Drugs (by dial and ground) | 0.54 (0.27 to 1.08) | 26 | 6 | 35 | 33 | Dollars by family, $M: Sabatini 0.14, Pellegrino 0.03, Vannucci 0.19, Ferrante 0.18. Range half to double, *new* | 6.5 |")
rep("VI", "| **Pad (a cost)** | **1.6 (0.9 to 2.7)** | **0.41** | **0.30** | **0.53** | **0.36** | | 7.5 |",
    "| **Pad (a cost)** | **1.6 (0.9 to 2.7)** | **26** | **19** | **33** | **22** | Dollars by family, $M: Sabatini 0.41, Pellegrino 0.30, Vannucci 0.53, Ferrante 0.36 | 7.5 |")
rep("VI", "the carting line (80 percent of $4.5M to Vannucci) and the Strip line (70 percent of $3.6M)",
    "the carting line (89 percent of the $4.05M family pool to Vannucci) and the Strip line (78 percent of the $3.24M family pool)")
rep("VI", "| Port and union: the Irish side of the docks (Local 1201, Part V 3) | **$0.9M** | $0.4M to $1.6M | **The 25 percent of the $3.0M docks flow that does not go to Pellegrino ($0.75M, section 4.3), plus the Brigades' half of the cross-river items, $0.15M (tugs, lighterage and ship-side pilferage, the 50/50, Part V section 1 #1)** |",
    "| Port and union: the Irish side of the docks (Local 1201, Part V 3) | **$0.75M** | $0.4M to $1.6M | **The 25 percent of the $3.0M docks flow that does not go to Pellegrino (section 4.3). It includes the Brigades' half of the cross-river items (tugs, lighterage and ship-side pilferage, the 50/50, Part V section 1 #1). The Pellegrino half sits inside the other 75 percent** |")
rep("VI", "| **Total** | **$1.7M** | **$0.7M to $3.0M** | |", "| **Total** | **$1.5M** | **$0.7M to $3.0M** | |")
rep("VI", "| Brigades | **$1.7M** | **$0.7M to $3.0M** |", "| Brigades | **$1.5M** | **$0.7M to $3.0M** |")
rep("VI", "| Numbers banks, net, Eastside share | $0.8M | $0.15M to $1.5M |", "| Numbers banks, net, Eastside share | $0.83M | $0.15M to $1.5M |")
rep("VI", "| Bookmaking, net to the combine | **$0.3M** | **$0.1M to $0.8M** |", "| Bookmaking, net to the combine | **$0.32M** | **$0.1M to $0.8M** |")
rep("VI", "| **Combine's own lines** | **$1.1M** | **$0.25M to $2.3M** | |", "| **Combine's own lines** | **$1.15M** | **$0.25M to $2.3M** | |")
rep("VI", "| Eastside combine, own lines | **$1.1M** | **$0.25M to $2.3M** |", "| Eastside combine, own lines | **$1.15M** | **$0.25M to $2.3M** |")
rep("VI", "| Chinatown | **$0.5M** | **$0.2M to $1.3M** |", "| Chinatown | **$0.46M** | **$0.2M to $1.3M** |")
rep("VI", "| **Own lines, total** | **$9.4M** | |", "| **Own lines, total** | **$9.2M** | |")
rep("VI", "come to about $9.4M, and the shared drug pool adds about $9.1M, about $18.5M in all", "come to about $9.2M, and the shared drug pool adds about $9.1M, about $18.3M in all")
rep("VI", "(range $0.1M to $1.2M at the default handle)", "(range $0.1M to $1.2M, taking the ranges of handle, net and Italian share together)")
rep("VI", "| Pad, bad debt, cheating, variance | 0.145 default, 0.07 to 0.195 | **Design** |", "| Pad, bad debt, cheating, variance | 0.145 default, 0.075 to 0.195 | **Design** |")
rep("VI", "**The annual total is a separate Design figure and is not the sum of the weekly table.**",
    "**The annual total is a separate Design figure and is not the sum of the weekly table. Its default is about 300 officers on the Pad at a mean envelope of about $5,300 a year (about $100 a week). The table prices each rank, and the mix of ranks that gives that mean is left to the run.**")
rep("VI", "| 1984 to 1985 | Forfeiture and money-laundering laws |", "| 1984 to 1986 | Forfeiture law (1984) and money-laundering law (1986) |")
rep("VI", "are the one family income that survives a prosecution of the rackets.",
    "are the one family income that survives a prosecution of the rackets. **The $2.5M of Sabatini front profit does not include the Sabatini construction firms (section 3.4, $1.0M), which are counted under the Concrete Club line in 9.3A. The two are separate and are not to be added twice.**")
# ---- Index
rep("idx", " Nothing has been loaded into the engine.", "")

for p, v in T.items():
    (D / F[p]).write_text(v, encoding="utf-8", newline="")
if bad:
    print("FAILED anchors:"); [print(" ", b) for b in bad]; sys.exit(1)
print("all edits applied")

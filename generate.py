#!/usr/bin/env python3
"""
PAC-COMMITS - generate an animated pixel-art Pac-Man SVG from a GitHub
contribution graph. Pac-Man sweeps the grid eating contribution cells; the
biggest-contribution days are power pellets that turn ghosts frightened-blue so
he can eat them. Pure SMIL animation (no JS) -> renders in a GitHub README.

Usage (CI):  GH_USER=you GITHUB_TOKEN=*** python generate.py
Without a token it falls back to realistic fake data so the repo previews.
Outputs:  dist/pac-commits.svg (light)  +  dist/pac-commits-dark.svg (dark)
"""
import math, os, json, random, urllib.request

# ---- themes ------------------------------------------------------------------
THEMES = {
    "light": dict(empty="#ebedf0",
                  levels=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
                  orb="#fff3c4"),
    "dark":  dict(empty="#161b22",
                  levels=["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
                  orb="#fff3c4"),
}
PAC = "#ffd22a"
FRIGHT = "#2733e8"
GHOST_COLORS = ["#ff0000", "#ffb8ff", "#00ffff", "#ffb852"]

# ---- geometry ----------------------------------------------------------------
CELL, GAP, MARGIN, PS = 13, 4, 18, 1.3
STEP = CELL + GAP
SPN = 13
CPS = 17.0     # cells per second -> derives the loop length
FD = 3.8       # frightened window (s) per power pellet

# ---- GitHub data -------------------------------------------------------------
LEVELMAP = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
            "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
GQL = """query($user:String!){user(login:$user){contributionsCollection{
contributionCalendar{weeks{contributionDays{contributionLevel weekday}}}}}}"""

def fetch_levels(user, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": GQL, "variables": {"user": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "pac-commits"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    cols = len(weeks)
    grid = [[0]*cols for _ in range(7)]
    for c, wk in enumerate(weeks):
        for d in wk["contributionDays"]:
            grid[d["weekday"]][c] = LEVELMAP.get(d["contributionLevel"], 0)
    return grid

def fake_levels(cols=53):
    random.seed(11)
    grid = [[0]*cols for _ in range(7)]
    for c in range(cols):
        streak = random.random() < 0.5
        for r in range(7):
            base = random.random()
            if streak and r in (1, 2, 3, 4, 5):
                base += 0.35
            grid[r][c] = (0 if base < .45 else 1 if base < .65 else 2 if base < .82
                          else 3 if base < .94 else 4)
    return grid

# ---- sprites -----------------------------------------------------------------
PAC_CLOSED = ["....#####....","..#########..",".###########.",".###########.",
    "#############","#############","#############","#############","#############",
    ".###########.",".###########.","..#########..","....#####...."]
PAC_OPEN = ["....#####....","..#######....",".######......",".#####.......",
    "#####........","###..........","##...........","###..........","#####........",
    ".#####.......",".######......","..#######....","....#####...."]
GHOST_BODY = ["....#####....","..#########..",".###########.","#############",
    "#############","#############","#############","#############","#############",
    "#############","#############","##.##.##.##.#","#..#...#...#."]
ORB = [".###.","#####","#####","#####",".###."]

def pixmap(rows, color=None, ps=PS):
    h, w = len(rows), len(rows[0]); out = []
    fill = f' fill="{color}"' if color else ""
    for ry, line in enumerate(rows):
        for cxi, ch in enumerate(line):
            if ch == "#":
                out.append(f'<rect x="{(cxi-w/2)*ps:.2f}" y="{(ry-h/2)*ps:.2f}" '
                           f'width="{ps:.2f}" height="{ps:.2f}"{fill}/>')
    return "".join(out)

def eyes(look):
    out = []; dx, dy = look
    for ex in (-3.2, 2.0):
        out.append(f'<rect x="{ex*PS:.2f}" y="{-3.0*PS:.2f}" width="{2.4*PS:.2f}" '
                   f'height="{3.2*PS:.2f}" rx="{PS:.2f}" fill="#fff"/>')
        out.append(f'<rect x="{(ex+0.7+dx*0.9)*PS:.2f}" y="{(-2.0+dy*0.9)*PS:.2f}" '
                   f'width="{1.3*PS:.2f}" height="{1.6*PS:.2f}" fill="#1414ff"/>')
    return "".join(out)

# ---- timeline helpers --------------------------------------------------------
def _kt_vals(base, points):
    pts = [(0.0, base)] + [(f, v) for f, v in points if 0 < f < 0.9995]
    pts.sort(key=lambda p: p[0])
    kt, vals, lastf = [], [], -1.0
    for f, v in pts:
        if f <= lastf: f = lastf + 1e-4
        kt.append(f"{f:.4f}"); vals.append(str(v)); lastf = f
    if kt[-1] != "1.0000": kt.append("1"); vals.append(str(base))
    return ";".join(kt), ";".join(vals)

def disc_anim(attr, base, points, cyc):
    kt, vals = _kt_vals(base, points)
    return (f'<animate attributeName="{attr}" calcMode="discrete" values="{vals}" '
            f'keyTimes="{kt}" dur="{cyc}s" repeatCount="indefinite"/>')

def scale_anim(points, cyc, base="1 1"):
    kt, vals = _kt_vals(base, points)
    return (f'<animateTransform attributeName="transform" type="scale" values="{vals}" '
            f'keyTimes="{kt}" dur="{cyc}s" repeatCount="indefinite"/>')

# ---- main builder ------------------------------------------------------------
def build_svg(levels, theme):
    T = THEMES[theme]
    ROWS = 7
    COLS = len(levels[0])
    W = MARGIN*2 + COLS*CELL + (COLS-1)*GAP
    H = MARGIN*2 + ROWS*CELL + (ROWS-1)*GAP
    N = ROWS*COLS
    CYCLE = max(16.0, N/CPS)

    def cx(c): return MARGIN + c*STEP + CELL/2
    def cy(r): return MARGIN + r*STEP + CELL/2

    order = []
    for r in range(ROWS):
        for c in (range(COLS) if r % 2 == 0 else range(COLS-1, -1, -1)):
            order.append((r, c))
    vis = {(r, c): i/(N-1) for i, (r, c) in enumerate(order)}

    def pac_pos(t):
        f = (t/CYCLE) % 1.0; s = f*(N-1); i = min(int(s), N-2); u = s-i
        (r0, c0), (r1, c1) = order[i], order[i+1]
        return (cx(c0)+(cx(c1)-cx(c0))*u, cy(r0)+(cy(r1)-cy(r0))*u)

    def gpos(co, k, t):
        frac = (t*k/CYCLE) % 1.0
        segs = [(co[a], co[(a+1) % 4],
                 math.hypot(co[(a+1) % 4][0]-co[a][0], co[(a+1) % 4][1]-co[a][1])) for a in range(4)]
        d = frac*sum(s[2] for s in segs)
        for p, q, L in segs:
            if d <= L:
                u = d/L if L else 0
                return (p[0]+(q[0]-p[0])*u, p[1]+(q[1]-p[1])*u)
            d -= L
        return co[0]

    # power pellets: biggest-contribution days, spread along the sweep
    cand = sorted([(r, c) for r in range(ROWS) for c in range(COLS) if levels[r][c] >= 4]
                  or [(r, c) for r in range(ROWS) for c in range(COLS) if levels[r][c] >= 3],
                  key=lambda rc: vis[rc])
    pellets, last = [], -1
    for cell in cand:
        if vis[cell]-last > 1.0/7:
            pellets.append(cell); last = vis[cell]
        if len(pellets) >= 6: break
    windows = [(vis[c]*CYCLE, min(vis[c]*CYCLE+FD, CYCLE)) for c in pellets]
    def in_win(t): return any(s <= t <= e for s, e in windows)

    # ghost regions as fractions of the grid (scale with COLS)
    def reg(c0, c1, r0, r1): return (cx(round(c0*(COLS-1))), cy(r0),
                                     cx(round(c1*(COLS-1))), cy(r1))
    REGIONS = [reg(0.04, 0.22, 0, 2), reg(0.28, 0.46, 3, 6),
               reg(0.54, 0.72, 0, 3), reg(0.78, 0.96, 2, 6)]
    LOOKS = [(1, 0), (-1, 0), (1, 0), (-1, 0)]

    DT, HIT, SEP = 0.05, CELL*1.05, 1.3
    def crossings(co, k, ph):
        ev, lst, t = [], -99.0, 0.0
        while t < CYCLE:
            px, py = pac_pos(t); gx, gy = gpos(co, k, t+ph)
            if math.hypot(px-gx, py-gy) < HIT and (t-lst) > SEP:
                ev.append(t); lst = t
            t += DT
        return ev

    ghosts = []
    for region, color, look in zip(REGIONS, GHOST_COLORS, LOOKS):
        co = [(region[0], region[1]), (region[2], region[1]),
              (region[2], region[3]), (region[0], region[3])]
        best = None
        for k in (1, 2, 3):
            ph = 0.0
            while ph < CYCLE/k + 1e-9:
                ev = crossings(co, k, ph)
                if ev:
                    sc = (1 if all(in_win(t) for t in ev) else 0, min(len(ev), 3))
                    if best is None or sc > best[0]:
                        best = (sc, k, ph, ev)
                ph += 0.2
        if best is None:
            best = ((0, 0), 1, 0.0, [])
        _, k, ph, ev = best
        ghosts.append(dict(co=co, color=color, look=look, k=k, phase=ph,
                           eaten=[t for t in ev if in_win(t)],
                           deaths=[t for t in ev if not in_win(t)]))

    eat = sorted(t for g in ghosts for t in g["eaten"])
    death = sorted(t for g in ghosts for t in g["deaths"])

    # cells
    cells = []
    for r in range(ROWS):
        for c in range(COLS):
            lvl = levels[r][c]; x, y = MARGIN+c*STEP, MARGIN+r*STEP
            base = T["levels"][lvl]
            rect = f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" fill="{base}">'
            if lvl >= 1:
                kt = max(vis[(r, c)], 0.001)
                rect += (f'<animate attributeName="fill" calcMode="discrete" '
                         f'values="{base};{T["empty"]};{T["empty"]}" '
                         f'keyTimes="0;{kt:.4f};1" dur="{CYCLE}s" repeatCount="indefinite"/>')
            cells.append(rect + "</rect>")

    # orbs (pixel, blink, vanish when eaten)
    orbs = []; blink = 0.34/CYCLE
    for (r, c) in pellets:
        eat_f = max(vis[(r, c)], 0.001)
        kt, vals, t, st = [], [], 0.0, 1
        while t < eat_f - 1e-6:
            kt.append(f"{t:.4f}"); vals.append(st); st ^= 1; t += blink
        kt.append(f"{eat_f:.4f}"); vals.append(0)
        if float(kt[-1]) < 0.999: kt.append("1"); vals.append(0)
        anim = (f'<animate attributeName="opacity" calcMode="discrete" '
                f'values="{";".join(map(str,vals))}" keyTimes="{";".join(kt)}" '
                f'dur="{CYCLE}s" repeatCount="indefinite"/>')
        orbs.append(f'<g transform="translate({cx(c):.1f},{cy(r):.1f})">'
                    f'{pixmap(ORB, T["orb"], ps=2.1)}{anim}</g>')

    # pac-man
    mpath = "M " + " L ".join(f"{cx(c):.1f} {cy(r):.1f}" for (r, c) in order)
    sp = []
    for te in eat:
        f = te/CYCLE
        sp += [(f, "1 1"), (f+0.12/CYCLE, "1.32 1.32"), (f+0.34/CYCLE, "1 1")]
    for td in death:
        f = td/CYCLE
        sp += [(f, "1 1"), (f+0.18/CYCLE, "0.45 0.45"), (f+0.45/CYCLE, "0 0"),
               (f+0.85/CYCLE, "0 0"), (f+0.95/CYCLE, "1 1")]
    pacman = f'''<g><g>{scale_anim(sp, CYCLE)}
<g opacity="1">{pixmap(PAC_OPEN, PAC)}<animate attributeName="opacity" values="1;0" keyTimes="0;0.5" calcMode="discrete" dur="0.34s" repeatCount="indefinite"/></g>
<g opacity="0">{pixmap(PAC_CLOSED, PAC)}<animate attributeName="opacity" values="0;1" keyTimes="0;0.5" calcMode="discrete" dur="0.34s" repeatCount="indefinite"/></g>
</g><animateMotion dur="{CYCLE}s" repeatCount="indefinite" rotate="auto" calcMode="linear" path="{mpath}"/></g>'''

    # ghosts
    gsvg = []
    for g in ghosts:
        co = g["co"]
        patrol = (f'M {co[0][0]:.1f} {co[0][1]:.1f} L {co[1][0]:.1f} {co[1][1]:.1f} '
                  f'L {co[2][0]:.1f} {co[2][1]:.1f} L {co[3][0]:.1f} {co[3][1]:.1f} Z')
        fpts = []
        for s, en in windows: fpts += [(s/CYCLE, FRIGHT), (en/CYCLE, g["color"])]
        opts = []
        for tc in g["eaten"]:
            f = tc/CYCLE; opts += [(f+0.05/CYCLE, "0.1"), (f+0.5/CYCLE, "1")]
        begin = f' begin="{-g["phase"]:.2f}s"' if g["phase"] > 0 else ""
        gsvg.append(f'''<g>{disc_anim("opacity","1",opts,CYCLE)}
<g fill="{g["color"]}">{pixmap(GHOST_BODY)}{disc_anim("fill",g["color"],fpts,CYCLE)}</g>
{eyes(g["look"])}
<animateMotion dur="{CYCLE}s" repeatCount="indefinite" calcMode="linear" path="{patrol}"{begin}/></g>''')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">\n<rect width="{W}" height="{H}" fill="none"/>\n'
            f'{"".join(cells)}\n{"".join(orbs)}\n{"".join(gsvg)}\n{pacman}\n</svg>')

# ---- entry -------------------------------------------------------------------
def main():
    user, token = os.environ.get("GH_USER"), os.environ.get("GITHUB_TOKEN")
    if user and token:
        try:
            levels = fetch_levels(user, token)
            print(f"fetched {len(levels[0])} weeks for {user}")
        except Exception as e:
            print(f"fetch failed ({e}); using fake data"); levels = fake_levels()
    else:
        print("no GH_USER/GITHUB_TOKEN; using fake data"); levels = fake_levels()
    os.makedirs("dist", exist_ok=True)
    open("dist/pac-commits.svg", "w").write(build_svg(levels, "light"))
    open("dist/pac-commits-dark.svg", "w").write(build_svg(levels, "dark"))
    print("wrote dist/pac-commits.svg + dist/pac-commits-dark.svg")

if __name__ == "__main__":
    main()

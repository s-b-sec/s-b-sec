#!/usr/bin/env python3
"""
Pac-Man Contribution Graph Generator
Fetches real GitHub contribution data and renders it as
an animated SVG — Pac-Man eats pellets (contributions),
four ghosts chase behind.
"""
import os
import sys
import requests

USERNAME = os.environ.get("GITHUB_USER", "s-b-sec")
TOKEN    = os.environ.get("GITHUB_TOKEN", "")

# Grid geometry
CELL  = 11
GAP   = 3
STEP  = CELL + GAP
PAD_X = 28
PAD_Y = 48

# Animation
DURATION    = 14.0          # seconds per full traversal
GHOST_OFFSETS = [2.0, 3.2, 4.4, 5.6]   # seconds behind Pac-Man

GHOST_COLORS = ["#FF0000", "#FFB8FF", "#00FFFF", "#FFB852"]

LEVEL_DARK  = ["#0e4429", "#006d32", "#26a641", "#39d353"]
LEVEL_LIGHT = ["#9be9a8", "#40c463", "#30a14e", "#216e39"]


# ── Data fetch ──────────────────────────────────────────────────────────────

def fetch_grid() -> list[list[int]]:
    """Return grid[col][row] = contribution count (0-N)."""
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays { contributionCount }
            }
          }
        }
      }
    }"""
    resp = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": {"login": USERNAME}},
        headers={"Authorization": f"bearer {TOKEN}"},
        timeout=15,
    )
    resp.raise_for_status()
    weeks = (
        resp.json()
        ["data"]["user"]["contributionsCollection"]
        ["contributionCalendar"]["weeks"]
    )
    return [[d["contributionCount"] for d in w["contributionDays"]] for w in weeks]


# ── Geometry helpers ─────────────────────────────────────────────────────────

def center(col: int, row: int) -> tuple[float, float]:
    return PAD_X + col * STEP + CELL / 2, PAD_Y + row * STEP + CELL / 2


def snake_order(grid: list[list[int]]) -> list[tuple[int, int, int]]:
    """Boustrophedon traversal — left→right on even rows, right→left on odd."""
    rows = max(len(col) for col in grid)
    order = []
    for row in range(rows):
        cols = range(len(grid)) if row % 2 == 0 else range(len(grid) - 1, -1, -1)
        for col in cols:
            if row < len(grid[col]):
                order.append((col, row, grid[col][row]))
    return order


# ── SVG builder ──────────────────────────────────────────────────────────────

def build_svg(grid: list[list[int]], dark: bool = False) -> str:
    cols = len(grid)
    rows = max(len(c) for c in grid)
    W = PAD_X * 2 + cols * STEP
    H = PAD_Y + rows * STEP + 32

    BG    = "#0d1117" if dark else "#f6f8fa"
    EMPTY = "#21262d" if dark else "#ebedf0"
    LVLS  = LEVEL_DARK if dark else LEVEL_LIGHT
    EYE   = BG  # Pac-Man eye colour matches background

    order = snake_order(grid)
    total = len(order)

    # ── Motion path (shared by all characters) ───────────────────────────────
    pts     = [center(c, r) for c, r, _ in order]
    mp_data = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    out: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────────
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
    )
    out.append(f'<rect width="{W}" height="{H}" rx="8" fill="{BG}"/>')

    # ── Contribution pellets ─────────────────────────────────────────────────
    out.append("<!-- pellets -->")
    for i, (col, row, count) in enumerate(order):
        x, y   = center(col, row)
        fill   = EMPTY if count == 0 else LVLS[min(count - 1, 3)]
        radius = 1.8 if count == 0 else 2.6 + min(count, 4) * 0.4

        eat_anim = ""
        if count > 0:
            t0 = i / total          # normalised arrival time
            t1 = min(t0 + 0.01, 1.0)
            # dot visible → vanishes when eaten → reappears at cycle restart
            eat_anim = (
                f'<animate attributeName="opacity" '
                f'values="1;1;0;0" '
                f'keyTimes="0;{t0:.4f};{t1:.4f};1" '
                f'dur="{DURATION}s" repeatCount="indefinite"/>'
            )

        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.2f}" fill="{fill}">'
            f'{eat_anim}</circle>'
        )

    # ── Hidden motion path ───────────────────────────────────────────────────
    out.append(f'<path id="mp" d="{mp_data}" fill="none" stroke="none"/>')

    # ── Pac-Man ──────────────────────────────────────────────────────────────
    # Path draws a full circle minus a wedge for the mouth.
    # "A9,9 0 1,0 9,-Y Z" traces the large arc; varying Y opens/closes mouth.
    open_mouth  = "M0,0 L9,3.5 A9,9 0 1,0 9,-3.5 Z"   # ~45° mouth
    mid_mouth   = "M0,0 L9,0.4 A9,9 0 1,0 9,-0.4 Z"   # almost closed
    close_mouth = "M0,0 L9,0.1 A9,9 0 1,0 9,-0.1 Z"   # fully closed

    out.append(
        f'<g id="pacman">'
        f'<animateMotion dur="{DURATION}s" repeatCount="indefinite" rotate="auto">'
        f'<mpath href="#mp"/></animateMotion>'
        # body (animated mouth)
        f'<path fill="#FFD700">'
        f'<animate attributeName="d" '
        f'values="{open_mouth};{mid_mouth};{close_mouth};{mid_mouth};{open_mouth}" '
        f'dur="0.32s" repeatCount="indefinite"/>'
        f'</path>'
        # eye
        f'<circle cx="2" cy="-5.5" r="1.6" fill="{EYE}"/>'
        f'</g>'
    )

    # ── Ghosts ───────────────────────────────────────────────────────────────
    out.append("<!-- ghosts -->")
    for gi, (gc, offset) in enumerate(zip(GHOST_COLORS, GHOST_OFFSETS)):
        # Ghost body: dome top + rectangular body + wavy skirt
        # Eyes look right by default (matches left→right dominant motion)
        ghost = (
            f'<g id="g{gi}">'
            f'<animateMotion dur="{DURATION}s" begin="-{offset}s" '
            f'repeatCount="indefinite" rotate="0">'   # ghosts don't tilt
            f'<mpath href="#mp"/></animateMotion>'
            # body dome
            f'<ellipse cx="0" cy="-3" rx="7" ry="8" fill="{gc}"/>'
            # body rect
            f'<rect x="-7" y="-3" width="14" height="8" fill="{gc}"/>'
            # wavy skirt
            f'<path d="M-7,5 Q-5.2,9 -3.5,5 Q-1.7,1 0,5 '
            f'Q1.7,9 3.5,5 Q5.2,1 7,5 L7,8 L-7,8 Z" fill="{gc}"/>'
            # white eyeballs
            f'<circle cx="-2.6" cy="-3.5" r="2.5" fill="white"/>'
            f'<circle cx="2.6"  cy="-3.5" r="2.5" fill="white"/>'
            # blue pupils
            f'<circle cx="-1.8" cy="-3" r="1.3" fill="#1a1aff"/>'
            f'<circle cx="3.4"  cy="-3" r="1.3" fill="#1a1aff"/>'
            f'</g>'
        )
        out.append(ghost)

    out.append("</svg>")
    return "\n".join(out)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs("dist", exist_ok=True)

    print(f"Fetching contributions for {USERNAME}...")
    grid = fetch_grid()
    print(f"  {len(grid)} weeks fetched.")

    print("Generating light SVG...")
    with open("dist/pacman.svg", "w") as f:
        f.write(build_svg(grid, dark=False))

    print("Generating dark SVG...")
    with open("dist/pacman-dark.svg", "w") as f:
        f.write(build_svg(grid, dark=True))

    print("Done.")


if __name__ == "__main__":
    main()

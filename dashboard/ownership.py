"""Shared ownership colors for tables and taxpayer editors."""

BLUE = "#6a8dad"
GREEN = "#6a9b7c"
PURPLE = "#9572ad"
UNASSIGNED = "#ad6a6a"
UNKNOWN = "#778493"


def slot_color(slot: str | None) -> str:
    if slot == "a":
        return BLUE
    if slot == "b":
        return GREEN
    if slot and slot.startswith("child_"):
        return PURPLE
    return UNASSIGNED


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def table_style(color: str, *, muted: bool = False) -> str:
    # Dataframe backgrounds require opaque colors. Match the editor's muted
    # 40% tint on the dark table surface; excluded records use half the tint.
    alpha = 0.2 if muted else 0.4
    background = "#" + "".join(
        f"{round(channel * alpha + base * (1 - alpha)):02x}"
        for channel, base in zip(rgb(color), rgb("#0e1117"))
    )
    foreground = "#b4bac4" if muted else "#f8fafc"
    return f"background-color: {background}; color: {foreground}"


def editor_styles() -> str:
    rules = []
    for kind, color in (("a", BLUE), ("b", GREEN), ("child", PURPLE), ("unassigned", UNASSIGNED)):
        channels = ", ".join(map(str, rgb(color)))
        selector = f'div[class*="st-key-owner_{kind}_"]'
        rules.append(f"""
{selector} {{
    background-color: rgba({channels}, 0.4);
    border-left: 3px solid {color};
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
}}
{selector} [data-baseweb="select"] > div {{
    border-color: rgba({channels}, 0.5);
}}
""")
    return "\n".join(rules)


def editor_key(slot: str | None, suffix: str) -> str:
    kind = "child" if slot and slot.startswith("child_") else slot
    if kind not in ("a", "b", "child"):
        kind = "unassigned"
    return f"owner_{kind}_{suffix}"

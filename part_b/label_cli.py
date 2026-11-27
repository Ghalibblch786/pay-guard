"""Label one record at a time in YOUR OWN terminal. Shows sanitized text locally, saves each answer to labels.csv immediately.

  .venv/bin/python -m part_b.label_cli            # resumes at the first unlabeled record; target 30
  .venv/bin/python -m part_b.label_cli --upto 60

Run it in macOS Terminal, never in an editor terminal or through an AI assistant: it prints complaint text.
It shows no model output, no sensitivity flag and no CFPB fields, and it suggests no answer. No network.
"""
import argparse, csv, io, os, re, shutil, sys, tempfile, textwrap
from pathlib import Path

from part_b.freeze_plan import LABEL_HEADER
from part_b.prompts import TAXONOMY

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "data" / "processed" / "labeling"
GUIDE = ROOT / "part_b" / "labeling_guide.md"
FIELDS = LABEL_HEADER.split(",")
CATEGORIES = [(c["id"], c["definition"]) for c in TAXONOMY["categories"]]
URGENCY = {"l": "low", "m": "medium", "h": "high"}
PRECEDENCE = ("If several fit, take the first: 1 fraud, 4 access/closure, 2 dispute, 3 payment, 5 fees, 6 conduct, 7 other.")
URGENCY_HELP = ("h = high: fraud maybe ongoing or money not recovered; cannot reach money needed now or hardship; deadline with serious loss; safety risk\n"
                "m = medium: unresolved problem with a current effect, not high\n"
                "l = low: information, feedback, or a past problem already resolved   (angry wording does not raise urgency)")
HUMAN_HELP = ("y if ANY: fraud/theft/scam/unauthorized; lawyer, lawsuit, court or escalation to another authority (filing THIS complaint does not count);\n"
              "alleged discrimination or law-breaking; safety, self-harm, abuse or threats; vulnerable person or severe hardship; too unclear to triage")


class Quit(Exception):
    pass


class Back(Exception):
    pass


def load_items(path: Path) -> list:
    parts = re.split(r"(?m)^=== ITEM (\d+) ===$", path.read_text(encoding="utf-8"))
    numbers = [int(n) for n in parts[1::2]]
    if not numbers or numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("the reading file does not contain items 1..N in order")
    return [text.strip() for text in parts[2::2]]


def load_rows(path: Path, n_items: int) -> list:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != n_items or [r.get("item") for r in rows] != [str(i) for i in range(1, n_items + 1)] or list(rows[0]) != FIELDS:
        raise ValueError("labels.csv does not have the expected header and one row per item")
    return rows


def save_rows(path: Path, rows: list) -> None:
    """Atomic and owner-only: a crash cannot leave a half-written sheet."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(buffer.getvalue())
    os.replace(tmp, path)


def is_labeled(row: dict) -> bool:
    return all((row.get(k) or "").strip() for k in ("category", "urgency", "requires_human"))


def ask(prompt: str, choices: dict, ask_input, show) -> str:
    """choices: typed answer -> stored value. q = quit, b = previous record, g = full guide."""
    while True:
        answer = ask_input(prompt).strip().lower()
        if answer == "q":
            raise Quit
        if answer == "b":
            raise Back
        if answer == "g":
            show(GUIDE.read_text(encoding="utf-8"))
        elif answer in choices:
            return choices[answer]
        else:
            show("Not a choice. Try again (q quit, b previous record, g full guide).")


def screen(n: int, target: int, text: str, width: int) -> str:
    body = "\n".join(textwrap.fill(line, width) for line in text.splitlines())
    menu = "\n".join(textwrap.fill(f"  {i}  {name}: {definition}", width, subsequent_indent="       ") for i, (name, definition) in enumerate(CATEGORIES, 1))
    return (f"RECORD {n} of {target}\n{'=' * width}\n{body}\n{'=' * width}\n"
            f"Judge ONLY from this text. Scroll up if it is long.\n\nCATEGORY (the main problem the company must solve)\n{menu}\n{PRECEDENCE}\n\n"
            f"URGENCY\n{URGENCY_HELP}\n\nNEEDS A HUMAN?\n{HUMAN_HELP}\n\nAt any question: q = quit (saved answers are kept), b = previous record, g = full guide\n")


def label_one(ask_input, show) -> dict:
    numbers = {str(i): name for i, (name, _) in enumerate(CATEGORIES, 1)}
    answer = {"category": ask("Category 1-7: ", numbers, ask_input, show),
              "urgency": ask("Urgency l/m/h: ", URGENCY, ask_input, show),
              "requires_human": ask("Needs a human y/n: ", {"y": "y", "n": "n"}, ask_input, show),
              "ambiguous": ask("Ambiguous? type y, or just press Enter: ", {"": "", "y": "y"}, ask_input, show)}
    show(f"-> {answer['category']} | {answer['urgency']} | human: {answer['requires_human']}" + (" | ambiguous" if answer["ambiguous"] else ""))
    return answer


def run(folder: Path, upto: int, ask_input=input, show=print, clear=lambda: None, width: int = 100) -> int:
    """Returns the number of consecutively labeled records from item 1."""
    items = load_items(folder / "items.txt")
    sheet = folder / "labels.csv"
    rows = load_rows(sheet, len(items))
    upto = min(upto, len(items))
    index = next((i for i, row in enumerate(rows[:upto]) if not is_labeled(row)), upto)
    try:
        while index < upto:
            clear(); show(screen(index + 1, upto, items[index], width))
            if is_labeled(rows[index]):
                r = rows[index]
                show(f"Already saved: {r['category']} | {r['urgency']} | human: {r['requires_human']}. Answer again to replace it.")
            try:
                answer = label_one(ask_input, show)
                if ask("Enter = save and continue, r = redo this record: ", {"": "save", "r": "redo"}, ask_input, show) == "redo":
                    continue
            except Back:
                index = max(index - 1, 0)
                continue
            rows[index].update(answer)
            save_rows(sheet, rows)
            index += 1
    except (Quit, KeyboardInterrupt, EOFError):
        pass
    return next((i for i, row in enumerate(rows) if not is_labeled(row)), len(rows))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--upto", type=int, default=30)
    args = ap.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Refusing to run: this prints complaint text, so run it yourself in an interactive terminal."); return 1
    try:
        done = run(FOLDER, args.upto, clear=lambda: print("\033[2J\033[3J\033[H", end=""),
                   width=min(shutil.get_terminal_size().columns, 100))
    except (ValueError, OSError) as e:
        print(f"FAIL: {e if isinstance(e, ValueError) else type(e).__name__}"); return 1
    print("\033[2J\033[3J\033[H", end="")
    print(f"Saved. Records labeled in order from the start: {done}" + ("  - target reached. Tell the assistant: labels done" if done >= args.upto else
          "  - run the same command to continue"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Kitab-bot fix patch #3 (run AFTER apply_patch.py and apply_patch2.py, inside the repo folder):
   python apply_patch3.py
Fixes strict search for names with punctuation / glued words:
  Grey's Anatomy, Money Heist: Korea, Moneyheist, "money heist?" ...
Edits bot.py only (backup: bot.py.bak3)."""
import os
import re
import shutil
import sys

NEW_TOKENS = '''def _words(text: str):
    """Letters/digits only: "Grey's Anatomy: S01!" -> ['greys', 'anatomy', 's01']"""
    text = re.sub(r"(https?://\\S+|www\\.\\S+|@\\w+)", " ", to_latin(text or ""))
    text = text.lower().replace("'", "").replace("\\u2019", "")
    return re.findall(r"[a-z0-9]+", text)


def _tokens(title: str):
    return _words(title)


'''

SECOND_CHANCE = '''    if STRICT_SEARCH and lwords:  # second chance: punctuation / glued words (Grey's, Moneyheist)
        pre = list({w[:3] for w in lwords if len(w) >= 2})
        if pre:
            results = dedupe(strict_filter(lwords, await store.find_any(pre, limit=1500)))
            if results:
                _top_title[" ".join(lwords)] = results[0][1]
                return results, False

    # typo tolerance:'''


def sub(s, old, new, label):
    assert s.count(old) == 1, f"anchor not found (or not unique): {label}"
    return s.replace(old, new, 1)


def main():
    if not os.path.exists("bot.py"):
        sys.exit("bot.py not found. Run this script inside the Kitab-bot folder.")
    with open("bot.py", encoding="utf-8") as f:
        s = f.read()
    if "def _words(" in s:
        print("bot.py: already patched, skipped")
        return
    assert "def strict_filter" in s and "def notify_requesters" in s, "Run apply_patch.py and apply_patch2.py first."

    s, n = re.subn(r"def _tokens\(title: str\):.*?\n\n\n", lambda m: NEW_TOKENS, s, count=1, flags=re.S)
    assert n == 1, "_tokens not found"
    s = sub(s, "        if core == q:", '        if core == q or "".join(core) == "".join(q):', "strict_filter tier 1")
    s = sub(
        s,
        "    words = norm(query).split()\n    latin = to_latin(query)\n    lwords = norm(latin).split() if latin != query else words\n",
        "    words = norm(query).split()\n    lwords = _words(query)\n",
        "run_search words",
    )
    s = sub(s, "    latin = to_latin(query)\n    lw = norm(latin).split()\n", "    lw = _words(query)\n", "suggest_names")
    s = sub(s, "\n    # typo tolerance:", "\n" + SECOND_CHANCE, "run_search second chance")

    old = '" ".join(norm(to_latin(query)).split())'
    assert s.count(old) >= 1, "query key not found"
    s = s.replace(old, '" ".join(_words(query))')

    shutil.copyfile("bot.py", "bot.py.bak3")
    with open("bot.py", "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print("bot.py: patched. Now: git add . && git commit -m 'Search fix' && git push")


if __name__ == "__main__":
    main()

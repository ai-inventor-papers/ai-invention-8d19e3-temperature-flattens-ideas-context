import json, re
T = json.load(open('work/tables.json'))
s = open('work/draft_template.md').read()
keys = set(re.findall(r"\{\{(\w+)\}\}", s))
missing = keys - set(T); assert not missing, missing
for k in keys:
    s = s.replace("{{" + k + "}}", T[k])
# house style: no dash runs. Table delimiter rows use a single hyphen per cell (valid GFM),
# and missing-value cells read "n/a" instead of a dash.
out = []
for line in s.split("\n"):
    if re.fullmatch(r"\|(\s*:?-+:?\s*\|)+", line):
        line = "|" + ":-|" * (line.count("|") - 1)
    out.append(line)
s = "\n".join(out).replace("| – |", "| n/a |")
open('paper_draft.md', 'w').write(s)
print("unused tables:", set(T) - keys)

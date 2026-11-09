"""Static sanity checks for main.tex (no LaTeX compiler needed): balanced environments, all figures exist,
every \\ref has a \\label, every \\cite has a \\bibitem."""
import re, pathlib, sys
here = pathlib.Path(__file__).parent; s = (here / "main.tex").read_text()
ok = True
envs = re.findall(r"\\(begin|end)\{([^}]+)\}", s); stack = []
for kind, name in envs:
    if kind == "begin": stack.append(name)
    elif not stack or stack.pop() != name: print("env mismatch at", name); ok = False
if stack: print("unclosed:", stack); ok = False
for f in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", s):
    if not (here / f).exists(): print("missing figure", f); ok = False
labels = set(re.findall(r"\\label\{([^}]+)\}", s))
for r in re.findall(r"\\(?:ref|eqref)\{([^}]+)\}", s):
    if r not in labels: print("undefined ref", r); ok = False
bib = set(re.findall(r"\\bibitem\{([^}]+)\}", s))
for c in re.findall(r"\\cite\{([^}]+)\}", s):
    for k in c.split(","):
        if k.strip() not in bib: print("undefined cite", k); ok = False
print("unused bib:", bib - {k.strip() for c in re.findall(r"\\cite\{([^}]+)\}", s) for k in c.split(",")})
print("figures:", len(re.findall(r"\\includegraphics", s)), "tables:", len(re.findall(r"\\begin\{table", s)),
      "words≈", len(re.sub(r"\\[a-zA-Z]+|[{}$%]", " ", s).split()))
print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)

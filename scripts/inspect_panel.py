import sys
sys.stdout.reconfigure(encoding='utf-8')
with open("web/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'class="panel"' in l or 'class="panel__head"' in l:
        print(f"Line {i+1}: {l.strip()}")
        for j in range(i, min(len(lines), i+35)):
            print(f"  {j+1}: {lines[j].strip()}")
        break

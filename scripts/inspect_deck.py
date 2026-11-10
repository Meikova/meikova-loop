import sys
sys.stdout.reconfigure(encoding='utf-8')
with open("web/index.html", "r", encoding="utf-8") as f:
    html = f.read()

deck_start = html.find('class="deck"')
deck_end = html.find('</div>', html.find('class="deck__vol"', deck_start)) + 6
print(html[deck_start:deck_end + 30])

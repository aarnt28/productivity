from pathlib import Path
text = Path("app/templates/tickets.html").read_text(encoding="utf-8")
print(text[text.index("const clientModalClose")-200:text.index("const clientModalClose")+50])

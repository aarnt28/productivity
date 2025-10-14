from pathlib import Path
text = Path("app/templates/tickets.html").read_text(encoding="utf-8")
idx = text.index('function applyNotePreviews')
print(text[idx:idx+1200])

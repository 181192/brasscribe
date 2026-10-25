"""Build screens.html: inline the Fretscribe Tab font and the outlined wordmark into screens.src.html."""
import base64, re
from pathlib import Path
here = Path(__file__).parent
font = base64.b64encode((here / "../brand/fonts/FretscribeTab-Regular.ttf").read_bytes()).decode()
word = (here / "../brand/wordmark.svg").read_text()
word = re.sub(r"<\?xml.*?\?>", "", word)
word = re.sub(r"<title.*?</title>", "", word, flags=re.S)
word = re.sub(r'fill="#[0-9A-Fa-f]{6}"', 'fill="currentColor"', word)
word = word.replace("<svg ", '<svg class="word" aria-hidden="true" ', 1).replace('role="img"', "").replace('aria-labelledby="title"', "")
src = (here / "screens.src.html").read_text()
(here / "screens.html").write_text(src.replace("{{TABFONT}}", font).replace("{{WORDMARK}}", word.strip()))

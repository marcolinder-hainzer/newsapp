"""Textwerkzeuge: Bereinigung, Tokenisierung, Satzzerlegung, Heuristiken."""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[0-9a-zäöüß]+(?:[-'][0-9a-zäöüß]+)*", re.IGNORECASE)
_SENT_RE = re.compile(r"(?<=[.!?…])[\"“”»«']?\s+(?=[\"„“»«'(]?[A-ZÄÖÜ0-9])")

STOPWORDS_DE = set("""
aber alle allem allen aller alles als also am an ander andere anderem anderen anderer anderes anderm andern
anders auch auf aus bei bin bis bist da damit dann das dass dein deine dem den denn der des dessen deshalb
die dies diese diesem diesen dieser dieses doch dort du durch ein eine einem einen einer eines einig einige
einigem einigen einiger einiges einmal er es etwas euch euer eure für gegen gewesen hab habe haben hat hatte
hatten hier hin hinter ich ihm ihn ihnen ihr ihre ihrem ihren ihrer ihres im in indem ins ist jede jedem
jeden jeder jedes jene jetzt kann kein keine keinem keinen keiner können könnte machen man manche mehr mein
meine mit muss musste nach nicht nichts noch nun nur ob oder ohne sehr sein seine seinem seinen seiner
seit sich sie sind so solche soll sollte sondern sonst über um und uns unser unter viel vom von vor
während war waren was weil welche welchem welchen welcher welches wenn werde werden wie wieder will wir
wird wirst wo wollen wollte würde würden zu zum zur zwar zwischen heute gestern morgen neue neuen neuer
mehr laut sagt sagte soll sollen wurde wurden worden jahr jahre jahren prozent mal beim seit rund etwa
erste ersten zwei drei vier fünf zehn bereits immer schon dabei sowie seien sei gibt geben gab neu
""".split())

STOPWORDS_EN = set("""
a about above after again against all am an and any are as at be because been before being below between
both but by can could did do does doing down during each few for from further had has have having he her
here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not
now of off on once only or other our ours out over own same she should so some such than that the their
theirs them themselves then there these they this those through to too under until up very was we were what
when where which while who whom why will with would you your yours new says said say year years per cent
percent also after amid over first two three four five ten could may might must one us told live latest
update updates news week day today yesterday tomorrow still back get gets got make makes made
""".split())

STOPWORDS = STOPWORDS_DE | STOPWORDS_EN

_DE_SUFFIXES = ("ungen", "ung", "heiten", "heit", "keiten", "keit", "ern", "ers", "en", "er", "es", "em", "e", "n", "s")
_EN_SUFFIXES = ("ations", "ation", "ings", "ing", "ies", "ied", "es", "ed", "s")

CLICKBAIT_PATTERNS = [
    r"\bschock", r"\bunglaublich", r"\bsensation", r"\bdas müssen sie", r"\bsie werden nicht glauben",
    r"\bkrass\b", r"\bhammer\b", r"\bdrama\b", r"\birre\b", r"\bwahnsinn", r"\bknall",
    r"\byou won'?t believe", r"\bshocking\b", r"\bslams?\b", r"\bdestroys?\b", r"\bblasts?\b",
    r"\bjaw-dropping\b", r"\bbombshell\b", r"\boutrage\b", r"\bfurious\b", r"\bhorror\b",
]
_CLICKBAIT_RE = re.compile("|".join(CLICKBAIT_PATTERNS), re.IGNORECASE)

OPINION_URL_HINTS = ("/meinung", "/kommentar", "/kommentare", "/opinion", "/commentisfree", "/kolumne",
                     "/kolumnen", "/debatte", "/standpunkt", "/gastbeitrag", "/leitartikel", "/editorial")
OPINION_TITLE_RE = re.compile(
    r"^(kommentar|meinung|kolumne|leitartikel|gastbeitrag|standpunkt|opinion|op-ed|editorial|analyse)\s*[:|–-]",
    re.IGNORECASE,
)

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "at_medium",
                   "at_campaign", "ns_mchannel", "ns_source", "ns_campaign", "ns_linkname", "ns_fee",
                   "cmpid", "ito", "xtor", "wt_mc", "wt.mc_id", "ref", "fbclid", "gclid", "traffic_source",
                   "dicbo", "smid"}


def clean_html(text: str | None, max_len: int | None = None) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = _WS_RE.sub(" ", text).strip()
    # Häufige Feed-Anhängsel entfernen
    text = re.sub(r"\s*\[?(weiterlesen|read more|continue reading)\]?\s*(\.{3}|…|»|›)?\s*$", "", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\s*(\[mehr\]|mehr\s*(\.{3}|…|»|›))\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*The post .{0,200} appeared first on .{0,100}\.?$", "", text)
    if max_len and len(text) > max_len:
        cut = text[:max_len]
        text = cut[: cut.rfind(" ")] + " …" if " " in cut else cut
    return text


def canonical_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS]
    return urlunparse((parsed.scheme or "https", parsed.netloc.lower(), parsed.path, "", urlencode(query), ""))


def _strip_accents_keep_umlauts(word: str) -> str:
    out = []
    for ch in word:
        if ch in "äöüß":
            out.append(ch)
            continue
        decomposed = unicodedata.normalize("NFKD", ch)
        out.append("".join(c for c in decomposed if not unicodedata.combining(c)))
    return "".join(out)


def stem(word: str) -> str:
    if len(word) <= 4 or word.isdigit():
        return word
    for suffix in _EN_SUFFIXES + _DE_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokenize(text: str, lang: str | None = None) -> list[str]:
    stops = STOPWORDS_DE if lang == "de" else STOPWORDS_EN if lang == "en" else STOPWORDS
    tokens = []
    for raw in _WORD_RE.findall(text.lower()):
        word = _strip_accents_keep_umlauts(raw).replace("'", "")
        if len(word) < 2 or word in stops:
            continue
        if word.isdigit() and len(word) < 3:
            continue
        tokens.append(stem(word))
        if "-" in word:  # Bindestrich-Komposita zusätzlich in ihre Teile zerlegen
            tokens.extend(stem(p) for p in word.split("-") if len(p) > 2 and p not in stops)
    return tokens


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def clickbait_hits(text: str) -> int:
    hits = len(_CLICKBAIT_RE.findall(text or ""))
    if text and text.count("!") >= 1:
        hits += 1
    letters = [c for c in text or "" if c.isalpha()]
    if letters:
        upper_words = [w for w in (text or "").split() if len(w) > 3 and w.isupper()]
        if len(upper_words) >= 2:
            hits += 1
    return hits


def looks_like_opinion(title: str, url: str) -> bool:
    lowered = (url or "").lower()
    if any(h in lowered for h in OPINION_URL_HINTS):
        return True
    return bool(OPINION_TITLE_RE.match((title or "").strip()))


def guess_language(text: str, default: str = "de") -> str:
    words = [w.lower() for w in _WORD_RE.findall(text or "")]
    if not words:
        return default
    de = sum(1 for w in words if w in STOPWORDS_DE)
    en = sum(1 for w in words if w in STOPWORDS_EN)
    if de == en:
        return default
    return "de" if de > en else "en"

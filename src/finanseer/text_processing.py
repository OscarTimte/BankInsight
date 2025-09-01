import re
from unidecode import unidecode

# A list of common, uninformative tokens found in bank descriptions
STOPWORDS = {
    "abn", "amro", "ing", "rabo", "rabobank", "knab", "bunq",
    "betaling", "betaalautomaat", "sepa", "ideal", "europe", "bv",
    "via", "trn", "iban", "bic", "pasnr", "datum", "tijd", "kenmerk",
    "omschrijving", "machtigingskenmerk", "incassant", "id", "eo", "en",
    "rabomobiel", "internetbankieren", "mobiel", "bankieren",
    "overboeking", "rekening", "naar", "van", "eo", "bij",
    "stichting", "payments", "online", "payment",
}

def normalize_description(text: str) -> str:
    """
    Normalizes a transaction description by:
    1. Converting to lowercase.
    2. Removing diacritics (e.g., 'é' -> 'e').
    3. Removing non-alphanumeric characters (except spaces).
    4. Removing common banking stopwords.
    5. Collapsing multiple spaces into one.

    Args:
        text: The raw description string.

    Returns:
        The normalized description string.
    """
    if not text:
        return ""

    # 1. Lowercase and 2. Remove diacritics
    text = unidecode(text.lower())

    # 3. Remove non-alphanumeric characters
    text = re.sub(r'[^a-z0-9\s]', ' ', text)

    # 4. Remove stopwords
    tokens = text.split()
    tokens = [token for token in tokens if token not in STOPWORDS]
    text = " ".join(tokens)

    # 5. Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()

    return text

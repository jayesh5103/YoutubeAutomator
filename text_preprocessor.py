"""
Text Preprocessor for TTS (Text-to-Speech)
==========================================
Runs 6 rule sets in sequence before every edge-tts call to produce
cleaner, more natural Hinglish voiceover for coding/DSA content.

Rule sets (in order):
  1. Complexity Notation  — O(n²) → "O of n squared"
  2. Code Symbol Cleanup  — curr_sum → "curr sum", != → "not equal to"
  3. Acronym Spelling      — DSA → "D S A", BFS → "B F S"
  4. Phonetic Fixes        — Trie → "Try", Dijkstra → "Dike-stra"
  5. Hindi Pause Injection — inserts natural breath pauses after punctuation
  6. Number Normalization  — 10000 → "ten thousand", 1e6 → "ten to the six"
"""

import re


# ─────────────────────────────────────────────────────────────────────────────
#  RULE 1: Complexity Notation
#  Expands Big-O / Theta / Omega into spoken form.
#  O(n²) → "O of n squared", O(n log n) → "O of n log n"
# ─────────────────────────────────────────────────────────────────────────────

# Superscript / Unicode exponent map
_SUPERSCRIPT_MAP = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
}

_EXPONENT_WORDS = {
    '0': 'to the zero',
    '1': '',           # n^1 is just n
    '2': 'squared',
    '3': 'cubed',
}

def _expand_exponent(exp_str: str) -> str:
    """Convert '2' → 'squared', '3' → 'cubed', '4' → 'to the four'."""
    exp_str = exp_str.strip()
    if exp_str in _EXPONENT_WORDS:
        return _EXPONENT_WORDS[exp_str]
    return f"to the {exp_str}"


def _expand_complexity_inner(inner: str) -> str:
    """Expand the content inside parentheses: n², 2^n, n log n, etc."""
    # Replace Unicode superscripts with ^digit
    for sup, digit in _SUPERSCRIPT_MAP.items():
        inner = inner.replace(sup, f'^{digit}')

    # Handle caret exponents: n^2 → "n squared", 2^n → "2 to the n"
    def _replace_caret(m):
        base = m.group(1).strip()
        exp = m.group(2).strip()
        word = _expand_exponent(exp)
        if word:
            return f"{base} {word}"
        return base

    inner = re.sub(r'(\w+)\s*\^\s*(\w+)', _replace_caret, inner)
    return inner


def rule_complexity_notation(text: str) -> str:
    """
    Expand O(...), Θ(...), Ω(...) notations into spoken English.
    Examples:
      O(n²)      → "O of n squared"
      O(n log n) → "O of n log n"
      O(1)       → "O of 1"
      O(2^n)     → "O of 2 to the n"
    """
    def _replace_match(m):
        symbol = m.group(1)   # O, Θ, Ω, Theta, Omega
        inner = m.group(2)
        expanded = _expand_complexity_inner(inner)
        # Normalize symbol names for speech
        symbol_spoken = {
            'O': 'O', 'o': 'O',
            'Θ': 'Theta', 'θ': 'Theta',
            'Ω': 'Omega', 'ω': 'Omega',
            'Theta': 'Theta', 'Omega': 'Omega',
        }.get(symbol, symbol)
        return f"{symbol_spoken} of {expanded}"

    # Match O(...), Θ(...), Ω(...), Theta(...), Omega(...)
    text = re.sub(
        r'\b(O|o|Θ|θ|Ω|ω|Theta|Omega)\s*\(\s*([^)]+)\s*\)',
        _replace_match,
        text
    )
    return text


# ─────────────────────────────────────────────────────────────────────────────
#  RULE 2: Code Symbol Cleanup
#  Converts programming symbols/operators into spoken words.
# ─────────────────────────────────────────────────────────────────────────────

# Operator replacements (order matters — longer patterns first)
_OPERATOR_MAP = [
    ('===', ' triple equals '),
    ('!==', ' not strict equal '),
    ('!=',  ' not equal to '),
    ('==',  ' equals '),
    ('>=',  ' greater than or equal to '),
    ('<=',  ' less than or equal to '),
    ('>>',  ' right shift '),
    ('<<',  ' left shift '),
    ('&&',  ' and '),
    ('||',  ' or '),
    ('->',  ' arrow '),
    ('=>',  ' arrow '),
    ('++',  ' plus plus '),
    ('--',  ' minus minus '),
    ('**',  ' power '),
]


def rule_code_symbols(text: str) -> str:
    """
    Clean code symbols for speech:
      - Underscores in identifiers → spaces (curr_sum → "curr sum")
      - Programming operators → spoken words
      - Curly braces, brackets → removed (they add noise in speech)
    """
    # Replace operators (must happen before underscore replacement)
    for symbol, spoken in _OPERATOR_MAP:
        text = text.replace(symbol, spoken)

    # Replace underscores between word characters (code identifiers)
    # curr_sum → "curr sum", max_val → "max val"
    text = re.sub(r'(?<=\w)_(?=\w)', ' ', text)

    # Remove stray code punctuation that doesn't belong in speech
    # Keep periods, commas, question marks, exclamation marks, colons, hyphens
    text = re.sub(r'[{}()\[\];]', ' ', text)

    # Clean up multiple spaces
    text = re.sub(r' {2,}', ' ', text)

    return text


# ─────────────────────────────────────────────────────────────────────────────
#  RULE 3: Acronym Spelling
#  Spells out uppercase acronyms letter-by-letter for TTS clarity.
# ─────────────────────────────────────────────────────────────────────────────

# Acronyms commonly used in DSA/coding content
# Maps acronym → spaced-out version or custom pronunciation
_ACRONYM_MAP = {
    'DSA':   'D S A',
    'BFS':   'B F S',
    'DFS':   'D F S',
    'DP':    'D P',
    'LRU':   'L R U',
    'LFU':   'L F U',
    'API':   'A P I',
    'SQL':   'S Q L',
    'OOP':   'O O P',
    'IDE':   'I D E',
    'GCD':   'G C D',
    'LCM':   'L C M',
    'BST':   'B S T',
    'AVL':   'A V L',
    'SDE':   'S D E',
    'FAANG': 'FAANG',      # Already pronounceable
    'MAANG': 'MAANG',
    'NQT':   'N Q T',
    'TCS':   'T C S',
    'KMP':   'K M P',
    'MST':   'M S T',
    'DAG':   'D A G',
    'XOR':   'X O R',
    'CPU':   'C P U',
    'GPU':   'G P U',
    'RAM':   'RAM',        # Already pronounceable
    'HTML':  'H T M L',
    'CSS':   'C S S',
    'JS':    'J S',
    'TC':    'T C',        # Time Complexity shorthand
    'SC':    'S C',        # Space Complexity shorthand
}


def rule_acronym_spelling(text: str) -> str:
    """
    Spell out known acronyms letter-by-letter.
    Also catches unknown 2-4 letter all-caps words and spaces them.
    """
    # First pass: replace known acronyms (case-sensitive, whole word)
    for acronym, spoken in _ACRONYM_MAP.items():
        text = re.sub(rf'\b{re.escape(acronym)}\b', spoken, text)

    # Second pass: catch remaining unknown all-caps words (2-4 chars)
    # that weren't in our map — spell them out
    def _spell_unknown(m):
        word = m.group(0)
        # Skip if it's already been spaced, or is a common word
        if ' ' in word or word in ('IN', 'OR', 'IF', 'DO', 'TO', 'NO', 'AT', 'ON', 'UP', 'OK'):
            return word
        return ' '.join(word)

    text = re.sub(r'\b[A-Z]{2,4}\b', _spell_unknown, text)

    return text


# ─────────────────────────────────────────────────────────────────────────────
#  RULE 4: Phonetic Fixes
#  Corrects TTS mispronunciations of CS/math terms.
# ─────────────────────────────────────────────────────────────────────────────

# Word → phonetic replacement (case-insensitive matching, output is the value)
_PHONETIC_FIXES = {
    'trie':         'try',
    'Trie':         'Try',
    'dijkstra':     'dike-stra',
    'Dijkstra':     'Dike-stra',
    'deque':        'deck',
    'Deque':        'Deck',
    'tuple':        'tupple',
    'Tuple':        'Tupple',
    'memoization':  'memo-ization',
    'Memoization':  'Memo-ization',
    'malloc':       'mal-ock',
    'calloc':       'cal-ock',
    'strcmp':        'string compare',
    'strlen':       'string length',
    'scanf':        'scan-f',
    'printf':       'print-f',
    'sudo':         'sue-doe',
    'nginx':        'engine-x',
    'kubectl':      'kube-control',
    'async':        'ay-sink',
    'enum':         'ee-num',
    'Enum':         'Ee-num',
    'char':         'kar',
    'segfault':     'seg-fault',
    'IEEE':         'I triple E',
    'regex':        'reg-ex',
    'OAuth':        'oh-auth',
    'FIFO':         'first in first out',
    'LIFO':         'last in first out',
    'leetcode':     'leet-code',
    'LeetCode':     'Leet-Code',
    'neetcode':     'neet-code',
    'NeetCode':     'Neet-Code',
    'geeksforgeeks':'geeks for geeks',
    'GeeksforGeeks':'Geeks for Geeks',
    'hashmap':      'hash map',
    'HashMap':      'Hash Map',
    'hashset':      'hash set',
    'HashSet':      'Hash Set',
    'treemap':      'tree map',
    'TreeMap':       'Tree Map',
    'substr':       'sub-string',
    'subarray':     'sub-array',
    'subarrays':    'sub-arrays',
}


def rule_phonetic_fixes(text: str) -> str:
    """
    Replace commonly mispronounced CS terms with phonetic hints.
    Uses whole-word matching to avoid corrupting partial matches.
    """
    for wrong, right in _PHONETIC_FIXES.items():
        # Use word boundary matching for safety
        text = re.sub(rf'\b{re.escape(wrong)}\b', right, text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
#  RULE 5: Hindi Pause Injection
#  Adds SSML-style breath pauses after Hindi sentence-ending patterns
#  and common Hinglish transition words for natural cadence.
# ─────────────────────────────────────────────────────────────────────────────

# Short pause character (comma adds ~200ms pause in edge-tts)
_SHORT_PAUSE = ','
# Medium pause (period adds ~400ms)
_MEDIUM_PAUSE = '.'

# Hindi/Hinglish words that benefit from a trailing micro-pause
_PAUSE_AFTER_WORDS = [
    'hai', 'hain', 'tha', 'the', 'thi',
    'dekho', 'suno', 'samjho', 'socho',
    'matlab', 'yaani', 'toh', 'lekin', 'aur',
    'pehle', 'phir', 'uske baad',
    'simple hai', 'easy hai', 'clear hai',
]


def rule_hindi_pauses(text: str) -> str:
    """
    Inject natural breath pauses after Hindi transition words and
    ensure punctuation spacing gives TTS proper cadence.
    """
    # Add micro-pause after common Hindi transition words
    # (only if not already followed by punctuation)
    for word in _PAUSE_AFTER_WORDS:
        # Match word at end of phrase (not followed by comma/period/!/?)
        pattern = rf'(\b{re.escape(word)})\b(?!\s*[,.\-!?;:])'
        text = re.sub(pattern, rf'\1{_SHORT_PAUSE}', text, flags=re.IGNORECASE)

    # Ensure em-dashes and long dashes create pauses
    text = re.sub(r'\s*[—–]\s*', f' {_MEDIUM_PAUSE} ', text)

    # Ensure ellipsis creates a longer pause
    text = text.replace('...', f' {_MEDIUM_PAUSE} ')
    text = text.replace('…', f' {_MEDIUM_PAUSE} ')

    # Clean up double punctuation that might result from injections
    text = re.sub(r'[,]{2,}', ',', text)
    text = re.sub(r'[.]{2,}', '.', text)
    text = re.sub(r',\.', '.', text)
    text = re.sub(r'\.,', '.', text)

    return text


# ─────────────────────────────────────────────────────────────────────────────
#  RULE 6: Number Normalization
#  Converts large numbers and scientific notation into spoken words.
# ─────────────────────────────────────────────────────────────────────────────

_NUMBER_WORDS = {
    100:        'hundred',
    1000:       'thousand',
    10000:      'ten thousand',
    100000:     'one lakh',       # Indian numbering
    1000000:    'ten lakh',
    10000000:   'one crore',
    100000000:  'ten crore',
}

# Ordered from largest to smallest for greedy matching
_NUMBER_THRESHOLDS = sorted(_NUMBER_WORDS.keys(), reverse=True)


def _number_to_words(n: int) -> str:
    """Convert an integer to approximate spoken Indian English."""
    if n < 0:
        return f"minus {_number_to_words(-n)}"
    if n < 100:
        return str(n)

    for threshold in _NUMBER_THRESHOLDS:
        if n >= threshold:
            count = n // threshold
            remainder = n % threshold
            word = _NUMBER_WORDS[threshold]

            # If the number is an exact match for a named threshold, use the label directly
            # e.g. 10000 → "ten thousand" (not "one ten thousand")
            if count == 1:
                result = word
            else:
                result = f"{count} {word}"

            if remainder > 0 and remainder >= 100:
                result += f" {_number_to_words(remainder)}"
            return result

    return str(n)


def rule_number_normalization(text: str) -> str:
    """
    Convert large numbers and scientific notation to spoken form.
    Examples:
      10000  → "ten thousand"
      1e6    → "ten to the 6"
      10^9   → "ten to the 9"
      100000 → "one lakh"
    """
    # Scientific notation: 1e6, 1e9, 10e3, etc.
    def _replace_sci(m):
        base = m.group(1)
        exp = m.group(2)
        if base == '1' or base == '10':
            return f"ten to the {exp}"
        return f"{base} times ten to the {exp}"

    text = re.sub(r'\b(\d+)[eE](\d+)\b', _replace_sci, text)

    # Power notation already handled by complexity rules, but catch standalone: 10^9
    def _replace_power(m):
        base = m.group(1)
        exp = m.group(2)
        return f"{base} to the {exp}"

    text = re.sub(r'\b(\d+)\s*\^\s*(\d+)\b', _replace_power, text)

    # Large integers (4+ digits, not part of a word/identifier)
    def _replace_large_number(m):
        num_str = m.group(0).replace(',', '')
        try:
            n = int(num_str)
            if n >= 1000:
                return _number_to_words(n)
        except ValueError:
            pass
        return m.group(0)

    # Match numbers with optional commas: 10,000 or 10000 (4+ digits)
    text = re.sub(r'\b\d{1,3}(?:,\d{3})+\b', _replace_large_number, text)  # comma-separated
    text = re.sub(r'\b\d{4,}\b', _replace_large_number, text)               # plain large numbers

    return text


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_for_tts(text: str) -> str:
    """
    Run all 6 rule sets in sequence. Order matters:
      1. Complexity notation (before symbols get stripped)
      2. Code symbols (clean underscores/operators)
      3. Acronym spelling (before phonetic fixes)
      4. Phonetic fixes (word-level corrections)
      5. Hindi pauses (cadence injection)
      6. Number normalization (last, so it doesn't interfere with O(n²) etc.)
    """
    text = rule_complexity_notation(text)
    text = rule_code_symbols(text)
    text = rule_acronym_spelling(text)
    text = rule_phonetic_fixes(text)
    text = rule_hindi_pauses(text)
    text = rule_number_normalization(text)

    # Final whitespace cleanup
    text = re.sub(r' {2,}', ' ', text).strip()

    return text


# ─────────────────────────────────────────────────────────────────────────────
#  STANDALONE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        # Complexity notation
        ("Time complexity O(n²) hai aur space O(1) hai.", 
         "Complexity → spoken"),
        # Code symbols
        ("Agar curr_sum != max_val toh update karo.",
         "Underscores + operators"),
        # Acronyms
        ("DSA mein BFS aur DFS bahut important hain.",
         "Acronym spacing"),
        # Phonetic fixes
        ("Trie data structure use karo, Dijkstra se shortest path nikalo.",
         "CS term pronunciation"),
        # Hindi pauses
        ("Dekho yeh simple hai lekin powerful hai — samjho isko.",
         "Hindi breath pauses"),
        # Number normalization
        ("Array mein 10000 elements hain aur complexity 1e6 hai.",
         "Large number expansion"),
        # Combined
        ("Bhai DSA mein Trie ka time complexity O(n) hai. curr_sum != 0 toh update karo. "
         "10000 nodes pe BFS lagao — simple hai!",
         "All rules combined"),
    ]

    for text, label in test_cases:
        result = preprocess_for_tts(text)
        print(f"\n{'─'*60}")
        print(f"  [{label}]")
        print(f"  IN:  {text}")
        print(f"  OUT: {result}")

    print(f"\n{'─'*60}")
    print("✅ All preprocessing rules executed successfully.")

"""LaTeX preprocessing pipeline for CAS engines.

Converts raw LaTeX from academic papers into CAS-parseable form
via a 4-phase pipeline: strip environments, remove typographical
commands, normalize synonyms, clean whitespace.
"""

from __future__ import annotations

import re

# Phase 1: Environment wrappers to strip
_ENV_PATTERNS = [
    r"\\begin\{equation\*?\}",    r"\\end\{equation\*?\}",
    r"\\begin\{align\*?\}",       r"\\end\{align\*?\}",
    r"\\begin\{gather\*?\}",      r"\\end\{gather\*?\}",
    r"\\begin\{multline\*?\}",    r"\\end\{multline\*?\}",
    r"\\begin\{eqnarray\*?\}",    r"\\end\{eqnarray\*?\}",
    r"\\\[",                       r"\\\]",
    r"\$\$",                       r"\$",
]

# Phase 2: Typographical commands to strip
_STRIP_COMMANDS = [
    r"\\left",  r"\\right",
    r"\\displaystyle",  r"\\textstyle",  r"\\scriptstyle",
    r"\\Big",  r"\\big",  r"\\bigg",  r"\\Bigg",
    r"\\,",  r"\\;",  r"\\:",  r"\\!",  r"\\quad",  r"\\qquad",
    r"&",  r"\\\\",  r"\\nonumber",  r"\\label\{[^}]*\}",
    r"\\tag\{[^}]*\}",
]

# Font commands: extract content from braces
_FONT_COMMANDS = [
    r"\\mathrm\{([^}]*)\}",
    r"\\mathbf\{([^}]*)\}",
    r"\\mathit\{([^}]*)\}",
    r"\\text\{([^}]*)\}",
    r"\\textit\{([^}]*)\}",
    r"\\boldsymbol\{([^}]*)\}",
    r"\\operatorname\{([^}]*)\}",
]

# Phase 3: Synonym mapping
_SYNONYMS = {
    r"\\dfrac":  r"\\frac",
    r"\\tfrac":  r"\\frac",
    r"\\ge":     r"\\geq",
    r"\\le":     r"\\leq",
    r"\\ne":     r"\\neq",
    r"\\to":     r"\\rightarrow",
    r"\\gets":   r"\\leftarrow",
    r"\\land":   r"\\wedge",
    r"\\lor":    r"\\vee",
    r"\\lnot":   r"\\neg",
    r"\\cdot":   "*",
    r"\\times":  "*",
}


def strip_environments(latex: str) -> str:
    """Phase 1: Remove math environment wrappers."""
    result = latex
    for pattern in _ENV_PATTERNS:
        result = re.sub(pattern, "", result)
    return result


def remove_typographical(latex: str) -> str:
    """Phase 2: Strip typographical commands and extract font command contents."""
    result = latex
    for pattern in _STRIP_COMMANDS:
        result = re.sub(pattern, "", result)
    for pattern in _FONT_COMMANDS:
        result = re.sub(pattern, r"\1", result)
    return result


def normalize_synonyms(latex: str) -> str:
    """Phase 3: Map alternative LaTeX commands to canonical forms."""
    result = latex
    for old, new in _SYNONYMS.items():
        result = result.replace(old, new)
    return result


def clean_whitespace(latex: str) -> str:
    """Phase 4: Collapse whitespace and remove redundant outer braces."""
    result = re.sub(r"\s+", " ", latex).strip()
    if result.startswith("{") and result.endswith("}"):
        inner = result[1:-1]
        if inner.count("{") == inner.count("}"):
            result = inner
    return result


def preprocess_latex(latex: str) -> str:
    """Full 4-phase LaTeX preprocessing pipeline."""
    result = latex
    result = strip_environments(result)
    result = remove_typographical(result)
    result = normalize_synonyms(result)
    result = clean_whitespace(result)
    return result

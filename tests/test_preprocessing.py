"""Tests for LaTeX preprocessing pipeline."""

from __future__ import annotations

from cas_service.preprocessing import (
    preprocess_latex,
    strip_environments,
    remove_typographical,
    normalize_synonyms,
    clean_whitespace,
)


def test_strip_environments():
    assert strip_environments(r"\begin{equation}x+1\end{equation}") == "x+1"
    assert strip_environments(r"\[y^2\]") == "y^2"
    assert strip_environments(r"$z$") == "z"


def test_remove_typographical():
    assert remove_typographical(r"\left( x \right)") == "( x )"
    assert remove_typographical(r"\mathrm{x}") == "x"
    assert remove_typographical(r"\mathbf{y}") == "y"
    assert remove_typographical(r"\text{abc}") == "abc"
    # Testing \ Big etc.
    assert remove_typographical(r"\Big( x \Big)") == "( x )"


def test_normalize_synonyms():
    assert normalize_synonyms(r"\dfrac{a}{b}") == r"\frac{a}{b}"
    assert normalize_synonyms(r"\ge") == r"\geq"
    assert normalize_synonyms(r"\cdot") == "*"


def test_clean_whitespace():
    assert clean_whitespace("  x  +  1  ") == "x + 1"
    assert clean_whitespace("{x+1}") == "x+1"
    assert clean_whitespace("{{y}}") == "{y}"
    assert clean_whitespace("{x} + {y}") == "{x} + {y}"
    assert clean_whitespace("{ {x} }") == " {x} "
    assert clean_whitespace("{x}}") == "{x}}"


def test_preprocess_full():
    latex = r"\begin{equation} \mathbf{x} + \left( y \right) \ge 0 \end{equation}"
    assert preprocess_latex(latex) == r"x + ( y ) \geq 0"

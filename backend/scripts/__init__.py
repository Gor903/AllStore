"""Operator commands: run with `python -m scripts.<name>`.

A package rather than loose files so the test suite can import what they do and check it.
Without it mypy sees the same file as two modules, and a test importing one of them is the
moment that surfaces.
"""

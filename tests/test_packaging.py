"""Tests for packaged resource availability."""

from __future__ import annotations

import importlib.resources as resources


def test_package_resources_include_demo_bundle():
    demo_bundle = resources.files("duecheck").joinpath("demo_data", "sample_bundle.json")
    assert demo_bundle.is_file()
    assert demo_bundle.read_text()


def test_package_resources_include_schemas():
    schema = resources.files("duecheck").joinpath("schemas", "ledger.schema.json")
    assert schema.is_file()
    assert schema.read_text()

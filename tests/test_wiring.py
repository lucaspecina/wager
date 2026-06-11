"""Scaffolding wiring test: the package imports and core deps are present."""

import wager


def test_package_imports():
    assert wager.__version__ == "0.1.0"


def test_core_dependencies_importable():
    import numpy
    import pandas
    import pydantic
    import scipy

    assert all(mod.__name__ for mod in (numpy, pandas, pydantic, scipy))

"""
Unittest wrapper around tests/validate.py: one test per planted-fault check,
so `python -m unittest discover -s tests -v` fails if any tool stops
recovering what make_data.py planted. The checks, tolerances and their
derivations live in validate.py; this file only turns each row into a test.
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import validate


class TestPlantedFaultsRecovered(unittest.TestCase):
    """Generated below: test_<check name> for every entry in validate.CHECKS."""


def _make_test(fn):
    def test(self):
        r = validate.run_check(fn)
        self.assertTrue(r.passed, f"{r.tool} {r.check}: planted {r.planted}, "
                                  f"recovered {r.recovered}, tolerance {r.tolerance}")
    return test


for _name, _fn in validate.CHECKS:
    setattr(TestPlantedFaultsRecovered, f"test_{_name}", _make_test(_fn))


if __name__ == "__main__":
    unittest.main()

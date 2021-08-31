#!/usr/bin/env python

import unittest

import pacdb

class VerCmpTest(unittest.TestCase):
    def _runtest(self, ver1: str, ver2:str, exp:int) -> None:
        with self.subTest("forward", ver1=ver1, ver2=ver2, exp=exp):
            self.assertEqual(pacdb.vercmp(ver1, ver2), exp)
            # and run its mirror case just to be sure
        with self.subTest("reverse", ver1=ver1, ver2=ver2, exp=exp):
            self.assertEqual(pacdb.vercmp(ver2, ver1), -exp)

    # all similar length, no pkgrel
    def test_similarlength(self):
        self._runtest("1.5.0", "1.5.0", 0)
        self._runtest("1.5.1", "1.5.0", 1)

    # mixed length
    def test_mixedlength(self):
        self._runtest("1.5.1", "1.5", 1)

    # with pkgrel, simple
    def test_pkgrel_simple(self):
        self._runtest("1.5.0-1", "1.5.0-1", 0)
        self._runtest("1.5.0-1", "1.5.0-2", -1)
        self._runtest("1.5.0-1", "1.5.1-1", -1)
        self._runtest("1.5.0-2", "1.5.1-1", -1)

    # with pkgrel, mixed lengths
    def test_pkgrel_mixedlength(self):
        self._runtest("1.5-1", "1.5.1-1", -1)
        self._runtest("1.5-2", "1.5.1-1", -1)
        self._runtest("1.5-2", "1.5.1-2", -1)

    # mixed pkgrel inclusion
    def test_mixed_pkgrel(self):
        self._runtest("1.5", "1.5-1", 0)
        self._runtest("1.5-1", "1.5", 0)
        self._runtest("1.1-1", "1.1", 0)
        self._runtest("1.0-1", "1.1", -1)
        self._runtest("1.1-1", "1.0", 1)

    # alphanumeric versions
    def test_alphanumeric_versions(self):
        self._runtest("1.5b-1", "1.5-1", -1)
        self._runtest("1.5b", "1.5", -1)
        self._runtest("1.5b-1", "1.5", -1)
        self._runtest("1.5b", "1.5.1", -1)

    # from the manpage
    def test_fromthemanpage(self):
        self._runtest("1.0a", "1.0alpha", -1)
        self._runtest("1.0alpha", "1.0b", -1)
        self._runtest("1.0b", "1.0beta", -1)
        self._runtest("1.0beta", "1.0rc", -1)
        self._runtest("1.0rc", "1.0", -1)

    # going crazy? alpha-dotted versions
    def test_alphadotted(self):
        self._runtest("1.5.a", "1.5", 1)
        self._runtest("1.5.b", "1.5.a", 1)
        self._runtest("1.5.1", "1.5.b", 1)

    # alpha dots and dashes
    def test_alphadotsanddashes(self):
        self._runtest("1.5.b-1", "1.5.b", 0)
        self._runtest("1.5-1", "1.5.b", -1)

    # same/similar content, differing separators
    def test_differingseparators(self):
        self._runtest("2.0", "2_0", 0)
        self._runtest("2.0_a", "2_0.a", 0)
        self._runtest("2.0a", "2.0.a", -1)
        self._runtest("2___a", "2_a", 1)

    # epoch included version comparisons
    def test_epochincluded(self):
        for epochsep in pacdb.EPOCH_SEPS:
            with self.subTest(epochsep=epochsep):
                self._runtest(f"0{epochsep}1.0", f"0{epochsep}1.0", 0)
                self._runtest(f"0{epochsep}1.0", f"0{epochsep}1.1", -1)
                self._runtest(f"1{epochsep}1.0", f"0{epochsep}1.0", 1)
                self._runtest(f"1{epochsep}1.0", f"0{epochsep}1.1", 1)
                self._runtest(f"1{epochsep}1.0", f"2{epochsep}1.1", -1)

    # epoch + sometimes present pkgrel
    def test_epoch_pkgrel(self):
        for epochsep in pacdb.EPOCH_SEPS:
            with self.subTest(epochsep=epochsep):
                self._runtest(f"1{epochsep}1.0", f"0{epochsep}1.0-1", 1)
                self._runtest(f"1{epochsep}1.0-1", f"0{epochsep}1.1-1", 1)

    # epoch included on one version
    def test_epoch_oneversion(self):
        for epochsep in pacdb.EPOCH_SEPS:
            with self.subTest(epochsep=epochsep):
                self._runtest(f"0{epochsep}1.0", "1.0", 0)
                self._runtest(f"0{epochsep}1.0", "1.1", -1)
                self._runtest(f"0{epochsep}1.1", "1.0", 1)
                self._runtest(f"1{epochsep}1.0", "1.0", 1)
                self._runtest(f"1{epochsep}1.0", "1.1", 1)
                self._runtest(f"1{epochsep}1.1", "1.1", 1)

if __name__ == "__main__":
    unittest.main()
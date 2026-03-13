#!/usr/bin/env python3
# Copyright (c) 2025 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Clear

"""
Tests for the integer division fix in gen_partition.py::partition_size_in_kb().

Before the fix, Python 3 float division caused bare-byte sizes to produce a
float string in the XML (e.g. "1.5"), which made ptool.py crash with ValueError
when it called int("1.5").
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
GEN_PARTITION = os.path.join(REPO_ROOT, 'gen_partition.py')
PTOOL = os.path.join(REPO_ROOT, 'ptool.py')


def gen_xml(size_arg):
    """Run gen_partition.py with a single partition of the given --size value
    and return the parsed XML root element."""
    conf = textwrap.dedent(f"""\
        --disk --type=emmc --size=67108864
        --partition --name=boot --size={size_arg} \
--type-guid=DEA0BA2C-CBDD-4805-B4F9-F428251C3E98
    """)
    with tempfile.TemporaryDirectory() as d:
        conf_path = os.path.join(d, 'partitions.conf')
        xml_path = os.path.join(d, 'partitions.xml')
        with open(conf_path, 'w') as f:
            f.write(conf)
        r = subprocess.run(
            [sys.executable, GEN_PARTITION, '-i', conf_path, '-o', xml_path],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f'gen_partition.py failed:\n{r.stderr}')
        return ET.parse(xml_path).getroot()


def size_in_kb(size_arg):
    root = gen_xml(size_arg)
    return root.find('.//partition').get('size_in_kb')


class TestPartitionSizeInKb(unittest.TestCase):

    def _assert_integer_string(self, val):
        """Fail if val looks like a float string (contains '.')."""
        self.assertNotIn('.', val,
                         f'size_in_kb must be an integer string, got "{val}"')

    def test_exact_kb_is_integer(self):
        """1024 bytes → "1", not "1.0"."""
        val = size_in_kb('1024')
        self._assert_integer_string(val)
        self.assertEqual(int(val), 1)

    def test_non_round_bytes_floors(self):
        """15872 bytes (1024 * 15.5) → "15" via floor division, not "15.5"."""
        val = size_in_kb('15872')
        self._assert_integer_string(val)
        self.assertEqual(int(val), 15)

    def test_sub_kb_bytes_is_zero(self):
        """512 bytes → "0", not "0.5"."""
        val = size_in_kb('512')
        self._assert_integer_string(val)
        self.assertEqual(int(val), 0)

    def test_kb_suffix_unchanged(self):
        """512KB → "512"."""
        self.assertEqual(int(size_in_kb('512KB')), 512)

    def test_mb_suffix_unchanged(self):
        """4MB → "4096"."""
        self.assertEqual(int(size_in_kb('4MB')), 4096)

    def test_gb_suffix_unchanged(self):
        """1GB → "1048576"."""
        self.assertEqual(int(size_in_kb('1GB')), 1048576)

    def test_ptool_does_not_crash_on_non_round_byte_size(self):
        """ptool.py must not raise ValueError for a bare non-round byte size.
        This was the observable symptom of the bug."""
        conf = textwrap.dedent("""\
            --disk --type=emmc --size=67108864
            --partition --name=boot --size=15872 \
--type-guid=DEA0BA2C-CBDD-4805-B4F9-F428251C3E98
        """)
        with tempfile.TemporaryDirectory() as d:
            conf_path = os.path.join(d, 'partitions.conf')
            xml_path = os.path.join(d, 'partitions.xml')
            with open(conf_path, 'w') as f:
                f.write(conf)
            subprocess.run(
                [sys.executable, GEN_PARTITION, '-i', conf_path, '-o', xml_path],
                capture_output=True, check=True)
            r = subprocess.run(
                [sys.executable, PTOOL, '-x', xml_path],
                capture_output=True, text=True, cwd=d)
        self.assertNotIn('ValueError', r.stderr + r.stdout)
        self.assertEqual(r.returncode, 0,
                         f'ptool.py crashed:\n{r.stderr}\n{r.stdout}')


if __name__ == '__main__':
    unittest.main(verbosity=2)

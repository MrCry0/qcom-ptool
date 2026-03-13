#!/usr/bin/env python3
# Copyright (c) 2025 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Clear

"""
Tests for the phys_part type inconsistency fix in gen_partition.py.

Before the fix, phys_part defaulted to integer 0 when --lun was absent but
was set to a string (e.g. "0") when --lun=0 was given. This caused a dict
with mixed key types, so a UFS config mixing explicit --lun=0 and no-lun
partitions produced two separate <physical_partition> elements for LUN 0
instead of one.
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


def parse_xml(conf_text):
    with tempfile.TemporaryDirectory() as d:
        conf_path = os.path.join(d, 'partitions.conf')
        xml_path = os.path.join(d, 'partitions.xml')
        with open(conf_path, 'w') as f:
            f.write(conf_text)
        r = subprocess.run(
            [sys.executable, GEN_PARTITION, '-i', conf_path, '-o', xml_path],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f'gen_partition.py failed:\n{r.stderr}')
        return ET.parse(xml_path).getroot()


class TestPhysPartTypeConsistency(unittest.TestCase):

    def test_no_lun_produces_one_physical_partition(self):
        """A partition without --lun goes into exactly one <physical_partition>."""
        conf = textwrap.dedent("""\
            --disk --type=emmc --size=67108864
            --partition --name=boot --size=512KB \
--type-guid=DEA0BA2C-CBDD-4805-B4F9-F428251C3E98
        """)
        root = parse_xml(conf)
        self.assertEqual(len(root.findall('physical_partition')), 1)

    def test_no_lun_and_explicit_lun0_share_one_physical_partition(self):
        """A partition without --lun and one with --lun=0 must land in the
        same <physical_partition>, not create a duplicate for LUN 0."""
        conf = textwrap.dedent("""\
            --disk --type=ufs --size=67108864
            --partition --name=boot --size=512KB \
--type-guid=DEA0BA2C-CBDD-4805-B4F9-F428251C3E98
            --partition --lun=0 --name=xbl --size=512KB \
--type-guid=DEA0BA2C-CBDD-4805-B4F9-F428251C3E98
        """)
        root = parse_xml(conf)
        phy_parts = root.findall('physical_partition')
        self.assertEqual(len(phy_parts), 1,
                         'Expected 1 <physical_partition> for LUN 0, '
                         f'got {len(phy_parts)}')
        self.assertEqual(len(phy_parts[0].findall('partition')), 2,
                         'Both partitions must be inside the single element')

    def test_different_luns_produce_separate_physical_partitions(self):
        """Partitions on different LUNs each get their own <physical_partition>."""
        conf = textwrap.dedent("""\
            --disk --type=ufs --size=67108864
            --partition --lun=0 --name=boot   --size=512KB \
--type-guid=DEA0BA2C-CBDD-4805-B4F9-F428251C3E98
            --partition --lun=1 --name=rootfs --size=512KB \
--type-guid=DEA0BA2C-CBDD-4805-B4F9-F428251C3E98
        """)
        root = parse_xml(conf)
        self.assertEqual(len(root.findall('physical_partition')), 2)

    def test_multiple_no_lun_partitions_all_in_one_physical_partition(self):
        """Multiple partitions without --lun all land in a single LUN 0 element."""
        conf = textwrap.dedent("""\
            --disk --type=emmc --size=67108864
            --partition --name=sbl  --size=512KB \
--type-guid=DEA0BA2C-CBDD-4805-B4F9-F428251C3E98
            --partition --name=tz   --size=512KB \
--type-guid=A053AA7F-40B8-4B1C-BA08-2F68AC71A4F4
            --partition --name=boot --size=512KB \
--type-guid=20117F86-E985-4357-B9EE-374BC1D8487D
        """)
        root = parse_xml(conf)
        phy_parts = root.findall('physical_partition')
        self.assertEqual(len(phy_parts), 1)
        self.assertEqual(len(phy_parts[0].findall('partition')), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# Copyright (c) 2025 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Clear

"""
Tests for the MBR disk signature endianness fix in ptool.py.

Before the fix, the 32-bit disk signature at MBR bytes 440-443 (offset 0x1B8)
was written big-endian. Per the UEFI Specification (section 5.2.1, Table 20)
and the MBR format it must be little-endian (LSB at byte 440).

The bug was latent when DISK_SIGNATURE=0x0 (default), but any non-zero value
produced a malformed protective MBR.
"""

import os
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PTOOL = os.path.join(REPO_ROOT, 'ptool.py')

# A non-palindrome signature so big-endian vs little-endian are distinguishable
DISK_SIGNATURE = 0x12345678

PARTITIONS_XML = textwrap.dedent(f"""\
    <?xml version="1.0" ?>
    <configuration>
        <parser_instructions>
        SECTOR_SIZE_IN_BYTES=512
        WRITE_PROTECT_BOUNDARY_IN_KB=0
        GROW_LAST_PARTITION_TO_FILL_DISK=false
        ALIGN_PARTITIONS_TO_PERFORMANCE_BOUNDARY=false
        PERFORMANCE_BOUNDARY_IN_KB=0
        DISK_SIGNATURE=0x{DISK_SIGNATURE:08X}
        </parser_instructions>
        <physical_partition>
            <partition label="boot" size_in_kb="512"
                       type="DEA0BA2C-CBDD-4805-B4F9-F428251C3E98"
                       bootable="false" readonly="true"
                       filename="" sparse="false"/>
        </physical_partition>
    </configuration>
""")


def generate_gpt(tmpdir):
    xml_path = os.path.join(tmpdir, 'test.xml')
    with open(xml_path, 'w') as f:
        f.write(PARTITIONS_XML)
    r = subprocess.run(
        [sys.executable, PTOOL, '-x', xml_path],
        capture_output=True, text=True, cwd=tmpdir)
    if r.returncode != 0:
        raise RuntimeError(f'ptool.py failed:\n{r.stderr}\n{r.stdout}')
    return os.path.join(tmpdir, 'gpt_main0.bin')


class TestMBRDiskSignatureEndianness(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.gpt_path = generate_gpt(self.tmpdir)
        with open(self.gpt_path, 'rb') as f:
            self.data = f.read()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_signature_bytes_are_little_endian(self):
        """Bytes 440-443 must store the signature LSB-first (little-endian)."""
        raw = self.data[440:444]
        # Expected layout for 0x12345678 little-endian: 78 56 34 12
        self.assertEqual(raw[0], 0x78, f'byte 440 should be LSB 0x78, got 0x{raw[0]:02X}')
        self.assertEqual(raw[1], 0x56, f'byte 441 should be 0x56, got 0x{raw[1]:02X}')
        self.assertEqual(raw[2], 0x34, f'byte 442 should be 0x34, got 0x{raw[2]:02X}')
        self.assertEqual(raw[3], 0x12, f'byte 443 should be MSB 0x12, got 0x{raw[3]:02X}')

    def test_signature_round_trips_as_little_endian_uint32(self):
        """Reading bytes 440-443 as a little-endian uint32 must recover the
        original DISK_SIGNATURE value."""
        raw = self.data[440:444]
        recovered, = struct.unpack_from('<I', raw)
        self.assertEqual(recovered, DISK_SIGNATURE,
                         f'Expected 0x{DISK_SIGNATURE:08X}, got 0x{recovered:08X}')

    def test_signature_is_not_big_endian(self):
        """Confirm the old (wrong) big-endian layout is not present."""
        raw = self.data[440:444]
        be_value, = struct.unpack_from('>I', raw)
        self.assertNotEqual(be_value, DISK_SIGNATURE,
                            'Bytes are in big-endian order — fix was not applied')


if __name__ == '__main__':
    unittest.main(verbosity=2)

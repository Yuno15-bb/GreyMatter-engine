#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""C Brain leak check: the guard that may block a commit.

Adapted from the earlier portfolio anonymization pipeline. It scans the files
that would ship and, with --history, their Git history. A surviving marker
causes exit status 1; a clean scan returns 0.

Usage:
  python3 leakcheck.py              scan the working tree
  python3 leakcheck.py --history    scan the tree and Git history
"""

import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# These tips were already public on 2026-09-26. History before them cannot be
# recalled; never add a tip here unless it has already been published.
ALREADY_PUBLIC = (
    "313bfec95b4c1cc0cce960464d2131bdfedfba76",  # main
    "dc28c37234a5e5ec418d9abddf5e8a7a81cfbcd0",  # fr
)

# Named private parties and secrets both block publication.
MARKERS = [
    ('client name', r"(?!)"),  # matched by fingerprints
    ('client acronym', r"(?!)"),  # matched by fingerprints
    ('client product', r"(?!)"),  # matched by fingerprints
    ('person — owner', r"(?!)"),  # matched by fingerprints
    ('person — manager', r"(?!)"),  # matched by fingerprints
    ('person — technician', r"(?!)"),  # matched by fingerprints
    ('person — executive', r"(?!)"),  # matched by fingerprints
    ('client family name', r"(?!)"),  # matched by fingerprints
    ('client city', r"(?!)"),  # matched by fingerprints
    ('client municipality', r"(?!)"),  # matched by fingerprints
    ('personal context', r"(?!)"),  # matched by fingerprints
    ('identified third party', r"(?!)"),  # matched by fingerprints
    ("local postal code", r"\b31\d{3}\b"),
    # In a diff, "+@contextlib.contextmanager" is an added decorator, not a mailbox:
    # the local part starts with a letter or a digit.
    ("email address",            r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("phone number",               r"(?<![\d.])0[1-9](?:[ .-]?\d{2}){4}(?![\d.])"),
    ("postal address",         r"\b\d{1,3}\s+(?:rue|avenue|impasse|chemin|boulevard|route)\s+\w+"),
    ("personal path",        r"/Users/[A-Za-z0-9_.-]+/"),
    ("Anthropic key",           r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    ("GitHub token",            r"gh[pousr]_[A-Za-z0-9]{16,}"),
    ("JWT token",               r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("plaintext assigned secret", r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}"),
]

# A fixed salt keeps the published table stable across installations. The table
# hides names from casual reading and indexing; it is not password encryption.
FINGERPRINT_SALT = "greymatter-leakcheck-v1:"
FINGERPRINTS = {
    "private project": [
        "1f179a15481724c5f43693085ba931ef44374fd8f4d155ffdbda935923c5c0f0",
        "37b3e281fdd7e4e006c5fa4725c0137c538c1ef11ea41908ea6ef383bbd39783",
        "6be743baf0f0af715908e2f4352bd96de0ec173da6aaff8f6618456ed012a29e",
        "b508e8babd559697dc6e1b5f57e1a2f28ff2fb5439b711c8c7e18c971d2d4988",
        "27e95d897fbc2002daa8c782daf881edfe9ff4baf62dad21cd6517c07d7a1950",
        "16183817c8825ca6431791c41f559987b319e4e1f70057760efe5b7a46613342",
        "2aba606d7907eb9d3179693bbbd55c5a0c86b55637c4593ca987389c98f31975",
    ],
    "client name": [
        "83e6abb979e679f30072cc6c5fcc22946c22f2e21b2f6d2af6a8898f7f4f8a90",
        "f3100b4145e3c79ba47b0e73b077873b81a066398381c87695ff0d7b5180273d"
    ],
    "client acronym": [
        "0596f5ff8c61ac08ed2edefb09ca6a0aaa9a2c3f6c03269fab15c72586c4d0f7"
    ],
    "client product": [
        "1f179a15481724c5f43693085ba931ef44374fd8f4d155ffdbda935923c5c0f0",
        "679e243768aa7da6315a8de2aafcb6124a77eac0fb5400efefe66b9d7fe7dc0a",
        "8057d28a401f16a3cd5b18d3b11a7835e5efd40b6a05b65cdf4cf0f5231e5d49"
    ],
    "person — owner": [
        "1bd266d9a62f2b85390babedf4b6e8a321e570a4381836428733a8a661faff71",
        "cec1534d223a7c09cfce00a695b5f05958aaba97a0d28d14eb0ebfe5124a2bda"
    ],
    "person — manager": [
        "aada6e93e01c6a1fb067e11f06bf497a4b08a229778bf7b30fe146b6e6b46557"
    ],
    "person — technician": [
        "b1112b42cd7a6b1a911edd18645b4c172e3daa99307f47d88ead21f7ae74a3e6"
    ],
    "person — executive": [
        "524d151bd6225c6418c6c48b88334e259756d7ac1c32c29710dfb6d41ee4e174"
    ],
    "client family name": [
        "944ec593772539e72907ef6d3a5795ff442a44da2a70654ca0529bf12fb5917d"
    ],
    "client city": [
        "5c76e96971d2f19c9397a1c2d8c1236389b8588fd6f1fa69056bfbc4734cfefc",
        "f0671961aebdddb80d1e5317aebffd1f69445ea790e096c89d4fa8c8b12782bf"
    ],
    "client municipality": [
        "4fd56e999c704f1c31db1a1d94e9a1f163d1964b15db97a170e99b4fc936215c",
        "6993b54a2001c2aca928fb4ddd517b80747adf47d92e44a7a417e7b887ea01ba",
        "6b520512baa54091112763dfe3fc500be7785acc7fd60c20d32b523c476fbe9a",
        "9f5d58a1f66d19b79869a440d8d215b4eae777a48449ec9f69aa753894bc9ac2",
        "f811d0bbff8d8a119a633b469a82a57c7cc370ce469f79b53c50dbdfa5d9ab9b",
        "fdee8516b79adef8ef75924a0f6b883a7125e7698d5461e3f11e8bd6eaba4c7f"
    ],
    "personal context": [
        "277727d80c35d065447163c6be353396c969dd5bc03d8198e94ee132bf575a0d",
        "6ac1ba2243c9e797dec0d0d8e7b5202edfdbe28f7d9fc5df73a0d2fea6dab5a4",
        "bfacb9549776c75f1174fa4cf044d80223151d9a871ae23208f8e724fb3664bb"
    ],
    "private identifier": [
        "cec1534d223a7c09cfce00a695b5f05958aaba97a0d28d14eb0ebfe5124a2bda",
        "7166c14592f08904f2d36e719bcd80dbcbe241f35f5cf4bca422f970d162fe67",
        "cca2c6645db1ca64fceb39fd584ce2dc66b8a62e20a066a211b61f0050c65634"
    ],
    "identified third party": [
        "0793bf8dec9a701e6c6dbc6f840afd790d6d7a8eb70f937117ab3a8df2269e60",
        "0e0645830b67d5b0e0647d35b8af5354f80cb6ac8f739a8f840a1610c514a4f8",
        "194298e9f73adf46cc9020324253cf8e41972e022fef53812fdd1d389f9dafcc",
        "26ea639fdea6f4d9b9fe69f258253fff3caef6d246082736b16d39639566c6c3",
        "2b6f962090cf1fe345eafcabf7064556f14f3334c5ff3805d817d1c14f939f84",
        "3a535d0630b3150ce43690b0682cc07542aa180f7e898de723549d31e0ffb200",
        "49a9f347b7c27f58e6f74a6d846bfd2d4101de10eb5c4206f05985f157c4e302",
        "556d351007ccb97a1d27c506303a2d7e866e4a67230ea1fd770b706774a3a754",
        "56d4e498322f22861c291ec91b979a8dd056836c7bb9d1927e780b451e348d44",
        "588f77b3721e525d5a49a4e8b39b33c6ec35dbf8ce5321fa25292c215b93c4fd",
        "664820f2105b1b7ba3314c110e2b74bb2a2e99af3b2f213a96a208519d970871",
        "70ade769e479f85019a0add5de9557ac02fa3b3d5506621f7b301ffc6d7cf9a5",
        "7b30836e4cde2be66369efe24de36326d792d94e406bf8d5685a1091c8c2d890",
        "a81c49a83512bbe4bdb2a800a06ec47e6423d8b8c477e0e49f711aab3c9790fd",
        "ad9b6d9467bad07f2797108af25d042334b08ede12ae7a3bbe89f4b25c89c899",
        "c847f40462b008c3fe3c827bc9b0c024a9d0c6b09c6009bc6efed2842d79ea2e",
        "d01c1a19e1fefb2f9f8fbaa75842f33751fede7527f0855dfe9abf5fd1c83a27",
        "dda006f013fb5ef76f3d0e8b71c9d5d4b91bf2b39841cf16e4a821cedc7eaaf0",
        "ddda3e02e2c8f8d62f691a5980c79c053baf2e48b8b36a9254b118252bffd444",
        "e438857d429318722be83e32656c5663ad5a29544c778554e5783416df2db462"
    ]
}

PRIVATE_NOTE_PATH_DIGESTS = {
    "547251209f16019ec69453645a55d3a5e0b3e4ffe07e41ad0c01e8b78c28271d",
    "982b729dc9f37e90cdfaa69bf3a1400e2dfe213ccdfe2a95bcc47e8f45c2c35c",
    "95136d5dc1891d0fa0d5c21e52a3e8ed6e1ce9d5e3b656e25849884417e11950",
    "fa232454c77fa75d706733771e0b0954312916fc7c81ecde9b8794bb41346de3",
    "0cf90851a310385df58b486df713ea2169b57730954d16291ed1538a9a908a93",
    "4cbde513f80768ef7c7f3afd3b1187579ac4fe410d835fcdfd8f520bc8f5fc03",
}
PRIVATE_NOTE_NAME_DIGESTS = {"c9589a5b680a5f643c43f341ba8d13c1d1e826fbd408df2ab7d0ab01b65b969a"}

MATCH_SHAPES = {
    "private identifier": {
        "cec1534d223a7c09cfce00a695b5f05958aaba97a0d28d14eb0ebfe5124a2bda": ["llllll"],
        "7166c14592f08904f2d36e719bcd80dbcbe241f35f5cf4bca422f970d162fe67": ["lll.lllll"],
        "cca2c6645db1ca64fceb39fd584ce2dc66b8a62e20a066a211b61f0050c65634": ["Ulllllll Ulllll"]
    },
    "client name": {
        "83e6abb979e679f30072cc6c5fcc22946c22f2e21b2f6d2af6a8898f7f4f8a90": [
            "UUUUUUUUUUU",
            "UUUllllllll"
        ],
        "f3100b4145e3c79ba47b0e73b077873b81a066398381c87695ff0d7b5180273d": [
            "UU UUUUUUUUU",
            "UU Ullllllll"
        ]
    },
    "client acronym": {
        "0596f5ff8c61ac08ed2edefb09ca6a0aaa9a2c3f6c03269fab15c72586c4d0f7": [
            "UUU",
            "lll-"
        ]
    },
    "client product": {
        "679e243768aa7da6315a8de2aafcb6124a77eac0fb5400efefe66b9d7fe7dc0a": [
            "UUUUUUU"
        ],
        "1f179a15481724c5f43693085ba931ef44374fd8f4d155ffdbda935923c5c0f0": [
            "UUU UUUU"
        ],
        "8057d28a401f16a3cd5b18d3b11a7835e5efd40b6a05b65cdf4cf0f5231e5d49": [
            "Ulll",
            "llll"
        ]
    },
    "person — owner": {
        "1bd266d9a62f2b85390babedf4b6e8a321e570a4381836428733a8a661faff71": [
            "Ullll"
        ],
        "cec1534d223a7c09cfce00a695b5f05958aaba97a0d28d14eb0ebfe5124a2bda": [
            "Ulllll"
        ]
    },
    "person — manager": {
        "aada6e93e01c6a1fb067e11f06bf497a4b08a229778bf7b30fe146b6e6b46557": [
            "Ulllllll"
        ]
    },
    "person — technician": {
        "b1112b42cd7a6b1a911edd18645b4c172e3daa99307f47d88ead21f7ae74a3e6": [
            "Ullllll"
        ]
    },
    "person — executive": {
        "524d151bd6225c6418c6c48b88334e259756d7ac1c32c29710dfb6d41ee4e174": [
            "Ullllll"
        ]
    },
    "client family name": {
        "944ec593772539e72907ef6d3a5795ff442a44da2a70654ca0529bf12fb5917d": [
            "Ullll"
        ]
    },
    "client city": {
        "5c76e96971d2f19c9397a1c2d8c1236389b8588fd6f1fa69056bfbc4734cfefc": [
            "Ulllllll"
        ],
        "f0671961aebdddb80d1e5317aebffd1f69445ea790e096c89d4fa8c8b12782bf": [
            "llllllllll"
        ]
    },
    "client municipality": {
        "f811d0bbff8d8a119a633b469a82a57c7cc370ce469f79b53c50dbdfa5d9ab9b": [
            "Ulllllll-Ullllll"
        ],
        "6993b54a2001c2aca928fb4ddd517b80747adf47d92e44a7a417e7b887ea01ba": [
            "Ullllllll"
        ],
        "6b520512baa54091112763dfe3fc500be7785acc7fd60c20d32b523c476fbe9a": [
            "Ullllll"
        ],
        "fdee8516b79adef8ef75924a0f6b883a7125e7698d5461e3f11e8bd6eaba4c7f": [
            "Ullllllllllll"
        ],
        "9f5d58a1f66d19b79869a440d8d215b4eae777a48449ec9f69aa753894bc9ac2": [
            "UUUUU"
        ]
    },
    "personal context": {
        "bfacb9549776c75f1174fa4cf044d80223151d9a871ae23208f8e724fb3664bb": [
            "Ullllll Ulllll"
        ],
        "6ac1ba2243c9e797dec0d0d8e7b5202edfdbe28f7d9fc5df73a0d2fea6dab5a4": [
            "UUU"
        ]
    },
    "identified third party": {
        "556d351007ccb97a1d27c506303a2d7e866e4a67230ea1fd770b706774a3a754": [
            "UUUUUUUUUU"
        ],
        "588f77b3721e525d5a49a4e8b39b33c6ec35dbf8ce5321fa25292c215b93c4fd": [
            "UUUUUUUU"
        ],
        "2b6f962090cf1fe345eafcabf7064556f14f3334c5ff3805d817d1c14f939f84": [
            "UUUUU"
        ],
        "26ea639fdea6f4d9b9fe69f258253fff3caef6d246082736b16d39639566c6c3": [
            "UUUUUU"
        ],
        "a81c49a83512bbe4bdb2a800a06ec47e6423d8b8c477e0e49f711aab3c9790fd": [
            "UUUUU"
        ],
        "70ade769e479f85019a0add5de9557ac02fa3b3d5506621f7b301ffc6d7cf9a5": [
            "UUUUUUUU"
        ],
        "e438857d429318722be83e32656c5663ad5a29544c778554e5783416df2db462": [
            "UUUUUUUUUU"
        ],
        "7b30836e4cde2be66369efe24de36326d792d94e406bf8d5685a1091c8c2d890": [
            "UUUUUUU"
        ],
        "ad9b6d9467bad07f2797108af25d042334b08ede12ae7a3bbe89f4b25c89c899": [
            "UUUUUUU"
        ],
        "664820f2105b1b7ba3314c110e2b74bb2a2e99af3b2f213a96a208519d970871": [
            "UUUUUU"
        ],
        "194298e9f73adf46cc9020324253cf8e41972e022fef53812fdd1d389f9dafcc": [
            "UUUUUU"
        ],
        "ddda3e02e2c8f8d62f691a5980c79c053baf2e48b8b36a9254b118252bffd444": [
            "UUUUUU"
        ],
        "d01c1a19e1fefb2f9f8fbaa75842f33751fede7527f0855dfe9abf5fd1c83a27": [
            "UUUUUUUU"
        ],
        "3a535d0630b3150ce43690b0682cc07542aa180f7e898de723549d31e0ffb200": [
            "UUUUUUU"
        ],
        "0793bf8dec9a701e6c6dbc6f840afd790d6d7a8eb70f937117ab3a8df2269e60": [
            "UUUUUUUU"
        ],
        "c847f40462b008c3fe3c827bc9b0c024a9d0c6b09c6009bc6efed2842d79ea2e": [
            "Ulllllll"
        ],
        "56d4e498322f22861c291ec91b979a8dd056836c7bb9d1927e780b451e348d44": [
            "Ullll"
        ],
        "dda006f013fb5ef76f3d0e8b71c9d5d4b91bf2b39841cf16e4a821cedc7eaaf0": [
            "Ulllll"
        ],
        "0e0645830b67d5b0e0647d35b8af5354f80cb6ac8f739a8f840a1610c514a4f8": [
            "Ulllll"
        ],
        "49a9f347b7c27f58e6f74a6d846bfd2d4101de10eb5c4206f05985f157c4e302": [
            "Ullll"
        ]
    }
}

def fingerprint(value: str) -> str:
    return hashlib.sha256((FINGERPRINT_SALT + value).encode("utf-8")).hexdigest()


def normalized_words(value: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFKD", value.lower())
                    if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", plain)


def surface_shape(value: str) -> str:
    return "".join("U" if c.isupper() else "l" if c.islower()
                   else "d" if c.isdigit() else " " if c.isspace()
                   else c for c in value)


def private_path_matches(value: str):
    for match in re.finditer(r"(?:projects|life)/[a-z0-9-]+", value, re.I):
        key = fingerprint(" ".join(normalized_words(match.group())))
        if key in PRIVATE_NOTE_PATH_DIGESTS:
            yield "private note path", match.start(), match.end()
    for match in re.finditer(r"[a-z0-9-]+", value, re.I):
        key = fingerprint(" ".join(normalized_words(match.group())))
        if key in PRIVATE_NOTE_NAME_DIGESTS:
            yield "private note name", match.start(), match.end()


def hashed_matches(source: str, value: str, fingerprints=FINGERPRINTS):
    lookup = {}
    for label, digests in fingerprints.items():
        if not exempted(label, source):
            for digest in digests:
                lookup.setdefault(digest, set()).add(label)
    words = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\w+", value)]
    for i in range(len(words)):
        for n in range(1, min(3, len(words) - i) + 1):
            group = words[i:i + n]
            norm = [part for word, _, _ in group for part in normalized_words(word)]
            if not norm or len(norm) > 3:
                continue
            keys = {fingerprint(" ".join(norm))}
            for label in set().union(*(lookup.get(key, ()) for key in keys)):
                if fingerprints is not FINGERPRINTS or label == "private project":
                    yield label, group[0][1], group[-1][2]
                    continue
                surface = value[group[0][1]:group[-1][2]]
                shapes = MATCH_SHAPES[label].get(next(key for key in keys if label in lookup.get(key, ())), ())
                actual = surface_shape(surface)
                if actual in shapes or (actual + "-") in shapes and value[group[-1][2]:].startswith("-"):
                    yield label, group[0][1], group[-1][2]


# These files contain their own guard patterns and cannot scan themselves.
SKIP_NAMES = {"leakcheck.py"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}

# Exemptions stay scoped to a marker and a path, never an entire marker family.
# The copyright holder may appear in reviewed documentation, licence notices,
# and plugin author fields. Other names and secrets still block those files.
# A manifest checksum can resemble a phone number; exempt only that marker.
EXEMPT = {
    "person — owner": [
        "6c5e5d5f3a6e244ac53a8f3ea40fe87ff18697bf809adddb719c53139bae4892",
        "6dbfb2d16f871018cb26cc929f47f675df747e3710322e1d468e6cbb91c7f813",
        "0a2d18f91639122cd3f5d96c7f446d483bd9b1622b324092618a54e322244048",
        "fa03a9f2789aaaf103171f7fb33ea30dedaace2daf4eaa5c9e4a7a0674e5ef3e"
    ],
    "phone number": [
        "69d74d046b34ed02407040f13c1956327c1c60afdbd547916ccfeac30ef1cd56"
    ]
}

# Copyright lines legally identify the holder. This exact header is excluded
# from the history scan; other appearances of the owner's name still block.
COPYRIGHT_HEADER = re.compile(r"Copyright \(c\) 20\d\d [A-Z][a-z]+ [A-Z][a-z]+")

# Exact false positives; broadening the mailbox pattern would hide real leaks.
FAUX_POSITIFS = {
    "email address": [
        "24fb00069b49b8f41e2ed612028ed5a9859f3a5b683f627d42c365544910c260"
    ]
}

# Synthetic test decoys are allowed only at exact values under tests/.
# A nearby value or the same value elsewhere must still fail the scan.
# Add a counterexample in tests/leakcheck_fixtures.py for every exception.
FIXTURES_DIRS = ("tests/",)
FIXTURES = {
    "personal path": [
        "13110ac81aaf2b11f00052cab4af8c01eff0f47020d1fbb67c22daef939e9692",
        "80fa6e9084c75252fcd01651a9f2bc0d58c1d63b6dda16b6933ba88a7a010b22",
        "813304161f1d2650bb6f351eeb7933dc7b6dced69589a65687e37eca7062e910"
    ],
    "Anthropic key": [
        "6510ada15041c6c697dd0007c832089a3d89a37aeb3974cd473bb7be9a099089"
    ],
    "plaintext assigned secret": [
        "70d4f73516ee597c11d749bfa6a409e6c547e26d35aadd87904a5b91c38c7575"
    ]
}


def est_un_leurre(label: str, source: str, valeur: str) -> bool:
    """True only for an exact decoy in the tests directory."""
    src = source[len("history:"):] if source.startswith("history:") else source
    if not src.startswith(FIXTURES_DIRS):
        return False
    return fingerprint(valeur) in FIXTURES.get(label, ())


def exempted(label: str, source: str) -> bool:
    # A historical version of a path receives the same narrow exemption.
    src = source[len("history:"):] if source.startswith("history:") else source
    return any(fingerprint(src[:i]) in EXEMPT.get(label, ())
               for i in range(1, len(src) + 1))


# Diff headers are Git metadata, not published content. Remove them before
# scanning history so a checksum is not mistaken for a telephone number.
DIFF_META = re.compile(r"^(diff --git |index [0-9a-f]+\.\.|--- |\+\+\+ |@@ |old mode |new mode |"
                       r"similarity index |rename (from|to) |new file mode |deleted file mode )")


def strip_diff_metadata(patch: str) -> str:
    return "\n".join(l for l in patch.splitlines() if not DIFF_META.match(l))


def added_lines(patch: str) -> str:
    """Keep only the lines each commit adds.

    A removed or unchanged line was added by an earlier commit, and that commit
    is scanned in turn unless it is already public. Reading removed lines turned
    the release commit red for taking names OUT of published files.
    """
    return "\n".join(l[1:] for l in patch.splitlines()
                     if l.startswith("+") and not DIFF_META.match(l))


def is_text(path: Path) -> bool:
    try:
        return b"\0" not in path.read_bytes()[:2048]
    except OSError:
        return False


def iter_files():
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file() or f.name in SKIP_NAMES:
            continue
        if SKIP_DIRS & set(f.relative_to(ROOT).parts):
            continue
        if is_text(f):
            yield f


def decoded_rule_values(node):
    """Yield every rule value, decoding explicitly encoded fields first."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key.endswith("_b64"):
                encoded = value.keys() if isinstance(value, dict) else [value]
                for item in encoded:
                    try:
                        yield base64.b64decode(item, validate=True).decode("utf-8")
                    except (binascii.Error, UnicodeDecodeError, ValueError):
                        yield str(item)
                if isinstance(value, dict):
                    yield from decoded_rule_values(list(value.values()))
            else:
                yield key
                yield from decoded_rule_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from decoded_rule_values(item)
    elif isinstance(node, str):
        yield node


def context(text, start, end, width=45):
    left = text[max(0, start - width):start].replace("\n", " ")
    right = text[end:end + width].replace("\n", " ")
    return f"…{left}⟦{text[start:end]}⟧{right}…"


def _sur_une_ligne_de_copyright(text: str, pos: int) -> bool:
    """Whether a match appears on a deliberate copyright or licence line."""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    line = text[start:end if end != -1 else len(text)]
    return "Copyright (c)" in line or "All rights reserved" in line


def scan(label_source, text, compiled, leaks):
    if label_source.startswith("history:"):
        text = "\n".join(l for l in text.splitlines() if not COPYRIGHT_HEADER.search(l))
    for label, rx in compiled:
        if exempted(label, label_source):
            continue
        for m in rx.finditer(text):
            if fingerprint(m.group(0)) in FAUX_POSITIFS.get(label, ()):
                continue
            if est_un_leurre(label, label_source, m.group(0)):
                continue
            if label == "person — owner" and _sur_une_ligne_de_copyright(text, m.start()):
                continue
            leaks.append((label_source, label, context(text, m.start(), m.end())))
    for label, start, end in (*hashed_matches(label_source, text), *private_path_matches(text)):
        if label == "person — owner" and _sur_une_ligne_de_copyright(text, start):
            continue
        leaks.append((label_source, label, context(text, start, end)))


def scan_history(root, compiled, public_tips):
    """Scan patches outside the reachable history of locally present public tips."""
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=60, check=True)

    paths = git("ls-files").stdout.splitlines()
    present = []
    for tip in public_tips:
        try:
            git("cat-file", "-e", f"{tip}^{{commit}}")
        except subprocess.CalledProcessError:
            continue
        present.append(tip)

    leaks = []
    n_hist = 0
    for rel in paths:
        if os.path.basename(rel) in SKIP_NAMES:
            continue
        patch = git("log", "-p", "--all", "--format=", *(
            ["--not", *present] if present else []), "--", rel).stdout
        if patch:
            n_hist += 1
            scan(f"history:{rel}", added_lines(patch), compiled, leaks)
    return leaks, n_hist, len(present)


def main():
    with_history = "--history" in sys.argv
    compiled = [(label, re.compile(pattern)) for label, pattern in MARKERS]
    leaks = []

    files = list(iter_files())
    for path in files:
        source = path.relative_to(ROOT).as_posix()
        content = path.read_text(encoding="utf-8", errors="replace")
        if path.name == "rules.json":
            try:
                values = decoded_rule_values(json.loads(content))
            except json.JSONDecodeError:
                scan(source, content, compiled, leaks)
            else:
                for value in values:
                    scan(source, value, compiled, leaks)
        else:
            scan(source, content, compiled, leaks)

    scanned = f"{len(files)} file(s)"

    if with_history:
        try:
            history_leaks, n_hist, excluded = scan_history(ROOT, compiled, ALREADY_PUBLIC)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"⛔ RED — Git history unreadable: {exc}")
            return 1
        leaks.extend(history_leaks)
        print(f"   {excluded} public tip(s) excluded from history")
        if n_hist:
            scanned += f" + history of {n_hist} file(s)"

    print(f"🔍 Leak check — {scanned}, {len(MARKERS)} markers")

    if not leaks:
        print("\n✅ CLEAN — no sensitive marker. Commit allowed.")
        return 0

    by_label = {}
    for _, label, _ in leaks:
        by_label[label] = by_label.get(label, 0) + 1

    print(f"\n⛔ RED — {len(leaks)} leak(s). Publication blocked.\n")
    for label, count in sorted(by_label.items(), key=lambda kv: -kv[1]):
        print(f"   {count:>5}×  {label}")

    print("\n   Examples:")
    for path, label, ctx in leaks[:20]:
        print(f"     · [{label}] {path}\n       {ctx}")
    if len(leaks) > 20:
        print(f"     … and {len(leaks) - 20} more.")

    print("\n   → Fix the source or its generalization rule; keep the markers strict.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

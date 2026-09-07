"""Make `src/` importable the same way it resolves at Lambda runtime.

The StreamProcessor Lambda is bundled from the `src/` directory itself (see
infrastructure/core_stack.py), so at runtime `contract` and
`stream_processor` are top-level modules, not `src.contract` /
`src.stream_processor`. Adding `src/` to sys.path here lets tests import
handlers and the shared contract module the exact same way.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

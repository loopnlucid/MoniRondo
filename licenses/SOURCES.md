# Sources and LGPL notice

MoniRondo uses the LGPLv3 editions of Qt, PySide6 and shiboken6, unmodified.
The release includes their corresponding source archives in this directory's
`sources` subdirectory (QtBase 6.12.0 and pyside-setup 6.12.0). Their exact
upstream URLs and SHA256 checksums are recorded in `sources/sources.json`.
QtBase contains all four Qt libraries shipped by MoniRondo: Core, Gui,
Widgets and Network, including the qwindows and qico plugins. PySide's source
archive includes shiboken. The build excludes QtPdf, QtQuick, VirtualKeyboard
and other unused Qt modules and plugins.

These libraries are dynamically linked. You may replace compatible DLLs and
Python extension modules in `_internal/PySide6` and `_internal/shiboken6`.
There are no signatures, integrity checks or restrictions that prevent such
replacement. You may reverse engineer the application to debug modifications
to the LGPL components. The complete MoniRondo source and build scripts
are provided alongside the binary and are licensed under MIT.

To reproduce the source archives before a release build, run:
`python scripts/prepare_third_party.py` (network access required).
The main build copies them together with the license texts into LICENSES.
For library build instructions, see the README/build documentation within
each upstream archive. Retain the full LGPLv3 and GPLv3 license texts.

# Third-party components and license notices

MoniRondo's own code (formerly MonitorSwap) is licensed under MIT; the full text is in `LICENSE`. Dependencies keep their respective licenses. No commercial Qt modules are used.

| Component | License / use |
|---|---|
| Python | PSF License; the interpreter is bundled by PyInstaller |
| PySide6, shiboken6 and the Qt libraries used | LGPLv3 / GPL / commercial multi-license; used here under LGPLv3 as dynamic libraries |
| pywin32 | PSF-based open-source license; the original text is included |
| PyInstaller | GPL with an exception for generated applications / bootloader |
| pywin32-ctypes | BSD-3-Clause |
| Other Qt/Python runtime components | their respective bundled notices and original texts |

The build script copies the installed license texts and the full LGPLv3/GPLv3 texts into `LICENSES`. That folder also lists package names, exact versions and the matching unmodified QtBase/PySide source archives with SHA256 checksums. The Qt/PySide libraries in the `_internal` folder are neither encrypted nor linked into a proprietary static library. Users may replace them within the terms of the LGPL and inspect them to debug their own modifications. There are no additional prohibitions on reverse engineering for debugging these components.

Sources and license information:

- Qt for Python: https://doc.qt.io/qtforpython-6/licenses.html
- LGPL obligations: https://www.qt.io/licensing/open-source-lgpl-obligations
- PySide6/shiboken sources: https://code.qt.io/cgit/pyside/pyside-setup.git/ (release tag matching the version in `LICENSES`)
- Qt sources and module sources: https://download.qt.io/official_releases/qt/ (matching version and `submodules` subfolder)
- pywin32: https://github.com/mhammond/pywin32 (matching build tag)
- Python: https://www.python.org/downloads/source/
- PyInstaller exception: https://pyinstaller.org/en/stable/license.html

MoniRondo does not modify these libraries. When redistributing, keep the complete release folder including license texts and source notices. After your own changes, verify that no additional GPL-only Qt modules are bundled.

"""Single source of truth for the build label shown by the app and the tools.

The .cmd launchers cannot import Python, so tests assert their literal label
still matches this constant. VERSION.json is metadata for the package.
"""
PRODUCT = 'Nexo Tesis'
VERSION = '0.4.1-dev'
BUILD = 'agentloop-1'

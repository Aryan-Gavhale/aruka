# Paste this into PythonAnywhere's WSGI file:
#   Web → your app → WSGI configuration file
#
# Replace YOURUSERNAME with your PythonAnywhere username (twice).

import sys

path = "/home/YOURUSERNAME/aruka"
if path not in sys.path:
    sys.path.insert(0, path)

from wsgi import application

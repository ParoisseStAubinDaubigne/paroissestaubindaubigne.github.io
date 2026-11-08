#!/usr/bin/env python3
"""Réduit une affiche ou une photo pour le site : largeur maximale 1200 px, JPEG qualité 82.

Usage : python3 -I outils/preparer_image.py <source> images/evenements/<id>.jpg
"""
import sys
from PIL import Image, ImageOps

src, dest = sys.argv[1], sys.argv[2]
im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
im.thumbnail((1200, 1800))
im.save(dest, "JPEG", quality=82, optimize=True)
print(dest, im.size)

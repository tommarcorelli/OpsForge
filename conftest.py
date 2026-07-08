"""Ajoute la racine du projet au sys.path pour que `modules.*` soit importable
depuis les tests, quel que soit le repertoire d'ou pytest est lance."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

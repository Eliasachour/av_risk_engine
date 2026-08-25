"""Ancre la racine du projet sur le sys.path pour que les paquets s'importent
(risk_engine, scenarios, world) quand on lance pytest depuis la racine."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

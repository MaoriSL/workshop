"""Scénarios d'attaque (laboratoire fictif confiné). Registre en LISTE BLANCHE : l'orchestrateur
ne peut lancer que ces scénarios, jamais une commande arbitraire."""
from .bruteforce import BruteForceScenario
from .combo import ComboScenario
from .dos import DoSScenario
from .exfiltration import ExfiltrationScenario
from .injection import InjectionScenario

SCENARIOS = {s.id: s for s in (DoSScenario(), BruteForceScenario(), InjectionScenario(), ExfiltrationScenario(), ComboScenario())}

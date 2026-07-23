"""
simulator package — Sales Simulation Engine (mercado espanhol).

Exports:
    SimulationEngine  — motor de simulação temporal dia a dia
    SimulationResult  — container com todas as tabelas geradas
    DEFAULT_CONFIG    — parâmetros padrão de simulação
"""

from erp.simulator.engine import SimulationEngine, SimulationResult
from erp.simulator.config import DEFAULT_CONFIG

__all__ = ["SimulationEngine", "SimulationResult", "DEFAULT_CONFIG"]

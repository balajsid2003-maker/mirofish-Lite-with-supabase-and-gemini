"""
业务服务模块 — MiroFish Lite (Gemini + Supabase)
"""

from .ontology_generator import OntologyGenerator
from .supabase_graph_builder import SupabaseGraphBuilderService
from .text_processor import TextProcessor
from .supabase_entity_reader import SupabaseEntityReader, EntityNode, FilteredEntities
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .simulation_manager import SimulationManager, SimulationState, SimulationStatus
from .simulation_config_generator import (
    SimulationConfigGenerator,
    SimulationParameters,
    AgentActivityConfig,
    TimeSimulationConfig,
    EventConfig,
    PlatformConfig,
)
from .simulation_runner import (
    SimulationRunner,
    SimulationRunState,
    RunnerStatus,
    AgentAction,
    RoundSummary,
)
from .simulation_ipc import (
    SimulationIPCClient,
    SimulationIPCServer,
    IPCCommand,
    IPCResponse,
    CommandType,
    CommandStatus,
)

# Backwards-compat alias so any code still using GraphBuilderService works
GraphBuilderService = SupabaseGraphBuilderService
ZepEntityReader = SupabaseEntityReader  # alias

__all__ = [
    "OntologyGenerator",
    "SupabaseGraphBuilderService",
    "GraphBuilderService",
    "TextProcessor",
    "SupabaseEntityReader",
    "ZepEntityReader",
    "EntityNode",
    "FilteredEntities",
    "OasisProfileGenerator",
    "OasisAgentProfile",
    "SimulationManager",
    "SimulationState",
    "SimulationStatus",
    "SimulationConfigGenerator",
    "SimulationParameters",
    "AgentActivityConfig",
    "TimeSimulationConfig",
    "EventConfig",
    "PlatformConfig",
    "SimulationRunner",
    "SimulationRunState",
    "RunnerStatus",
    "AgentAction",
    "RoundSummary",
    "SimulationIPCClient",
    "SimulationIPCServer",
    "IPCCommand",
    "IPCResponse",
    "CommandType",
    "CommandStatus",
]


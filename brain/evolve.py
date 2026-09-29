import os
import json
import re
import hashlib
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Import MOROAI core utilities (assumed to exist in the project structure)
try:
    from core.logger import get_logger
    from core.config import load_config
    from core.sandbox import execute_code_safely
except ImportError:
    # Fallbacks for standalone testing or if structure differs
    import logging
    import sys
    
    def get_logger(name):
        return logging.getLogger(name)
    
    def load_config():
        return {}
    
    def execute_code_safely(code, timeout=5):
        # Minimal safe execution wrapper for local testing
        # In production, this would use a proper sandbox
        try:
            exec(compile(code, "<string>", "exec"), {"__builtins__": {}}, {"__builtins__": {}})
            return {"success": True, "output": ""}
        except Exception as e:
            return {"success": False, "output": str(e)}

logger = get_logger("moroai.evolve")

@dataclass
class EvolutionProposal:
    """Represents a single proposed code modification."""
    file_path: str
    description: str
    original_content: str
    proposed_content: str
    reason: str
    risk_level: str = "low"  # low, medium, high
    status: str = "pending"  # pending, approved, rejected, applied, failed
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "description": self.description,
            "original_content": self.original_content,
            "proposed_content": self.proposed_content,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "status": self.status,
            "timestamp": self.timestamp
        }

@dataclass
class EvolutionReport:
    """Summary of the evolution analysis."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    total_files_analyzed: int = 0
    gaps_identified: List[str] = field(default_factory=list)
    proposals: List[EvolutionProposal] = field(default_factory=list)
    success: bool = False
    error_message: Optional[str] = None

class MOROAI_Evolver:
    """
    Core logic for MOROAI's self-improvement capabilities.
    Analyzes current state, identifies gaps, and proposes safe code modifications.
    """
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.config = load_config()
        self.evolution_log_path = self.base_dir / "logs" / "evolution_log.json"
        self._ensure_log_dir()
        
    def _ensure_log_dir(self):
        """Ensure the logs directory exists."""
        log_dir = self.base_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
    def analyze_current_state(self) -> Dict[str, Any]:
        """
        Analyze the current state of the MOROAI codebase.
        Returns a dictionary containing file contents, structure, and metadata.
        """
        logger.info("Analyzing current MOROAI state...")
        state = {
            "files": {},
            "structure": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # Define critical files to analyze
        critical_files = [
            "brain/evolve.py",
            "core/logger.py",
            "core/config.py",
            "core/sandbox.py",
            "main.py",
            "requirements.txt"
        ]
        
        for file_path in critical_files:
            full_path = self.base_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding='utf-8')
                    state["files"][file_path] = {
                        "content": content,
                        "hash": hashlib.md5(content.encode('utf-8')).hexdigest(),
                        "size": len(content)
                    }
                    state["structure"].append(file_path)
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
            else:
                state["files"][file_path] = {
                    "content": None,
                    "hash": None,
                    "size": 0,
                    "missing": True
                }
        
        state["total_files_analyzed"] = len(state["files"])
        return state

    def identify_gaps(self, state: Dict[str, Any]) -> List[str]:
        """
        Identify gaps in the current implementation based on the state.
        This is a heuristic analysis that can be extended with LLM calls.
        """
        logger.info("Identifying gaps in current implementation...")
        gaps = []
        
        # Example gap detection logic
        # 1. Check if error handling is robust
        for file_path, data in state["files"].items():
            if data["content"] is None:
                gaps.append(f"Missing critical file: {file_path}")
                continue
                
            content = data["content"]
            
            # Check for lack of type hints in critical modules
            if file_path.startswith("core/") or file_path.startswith("brain/"):
                if "def " in content and " -> " not in content:
                    gaps.append(f"Missing type hints in {file_path}")
                    
            # Check for lack of logging
            if "logger" not in content and "logging" not in content:
                gaps.append(f"No logging found in {file_path}")
                
            # Check for hardcoded values
            if re.search(r'password\s*=\s*["\'][^"\']+["\']', content):
                gaps.append(f"Potential hardcoded secret in {file_path}")
                
        # 2. Check for missing features based on roadmap (placeholder)
        # In a real implementation, this would query the roadmap and compare
        # with existing capabilities.
        
        if not gaps:
            gaps.append("No significant gaps identified. System appears stable.")
            
        logger.info(f"Identified {len(gaps)} gaps.")
        return gaps

    def generate_proposals(self, gaps: List[str], state: Dict[str, Any]) -> List[EvolutionProposal]:
        """
        Generate specific code modification proposals based on identified gaps.
        """
        logger.info("Generating evolution proposals...")
        proposals = []
        
        # Map gaps to potential solutions
        for gap in gaps:
            if "Missing type hints" in gap:
                file_path = gap.split(" in ")[1]
                proposal = self._propose_type_hints(file_path, state)
                if proposal:
                    proposals.append(proposal)
                    
            elif "No logging found" in gap:
                file_path = gap.split(" in ")[1]
                proposal = self._propose_logging(file_path, state)
                if proposal:
                    proposals.append(proposal)
                    
            elif "Missing critical file" in gap:
                file_path = gap.split("file: ")[1]
                proposal = self._propose_file_creation(file_path)
                if proposal:
                    proposals.append(proposal)
                    
            elif "Potential hardcoded secret" in gap:
                file_path = gap.split(" in ")[1]
                proposal = self._propose_secret_management(file_path, state)
                if proposal:
                    proposals.append(proposal)
        
        logger.info(f"Generated {len(proposals)} proposals.")
        return proposals

    def _propose_type_hints(self, file_path: str, state: Dict[str, Any]) -> Optional[EvolutionProposal]:
        """Propose adding type hints to a file."""
        data = state["files"].get(file_path)
        if not data or data["content"] is None:
            return None
            
        original = data["content"]
        # Simple heuristic: Add type hints to function definitions
        # In a real implementation, this would use an AST parser
        proposed = original
        
        # Example: Add return type to main function if missing
        if "def main()" in proposed and "def main() -> None" not in proposed:
            proposed = proposed.replace("def main()", "def main() -> None")
            
        if proposed == original:
            return None
            
        return EvolutionProposal(
            file_path=file_path,
            description="Add type hints to improve code clarity and safety",
            original_content=original,
            proposed_content=proposed,
            reason="Type hints help prevent runtime errors and improve IDE support",
            risk_level="low"
        )

    def _propose_logging(self, file_path: str, state: Dict[str, Any]) -> Optional[EvolutionProposal]:
        """Propose adding logging to a file."""
        data = state["files"].get(file_path)
        if not data or data["content"] is None:
            return None
            
        original = data["content"]
        proposed = original
        
        # Add logging import and logger

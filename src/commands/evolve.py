import os
import json
import hashlib
import difflib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

# Assuming MOROAI has a core configuration module
try:
    from moroai.config import MOROAI_HOME, CODEBASE_ROOT
except ImportError:
    # Fallback for standalone execution or testing
    MOROAI_HOME = Path.home() / ".moroai"
    CODEBASE_ROOT = Path(__file__).parent.parent.parent

@dataclass
class EvolutionProposal:
    """Represents a single proposed modification to the codebase."""
    file_path: str
    action: str  # 'create', 'modify', 'delete'
    description: str
    new_content: Optional[str] = None
    priority: int = 1  # 1 is highest
    rationale: str = ""

@dataclass
class EvolutionPlan:
    """Represents the full plan for an evolution step."""
    step_id: str
    timestamp: str
    proposals: List[EvolutionProposal] = field(default_factory=list)
    summary: str = ""
    confidence_score: float = 0.0

class CodebaseInspector:
    """Handles reading and analyzing the MOROAI codebase."""
    
    def __init__(self, root_path: Path = None):
        self.root_path = root_path or CODEBASE_ROOT
        self.excluded_dirs = {'__pycache__', '.git', 'node_modules', '.venv', 'venv', 'dist', 'build', '.mypy_cache', '.pytest_cache'}
        self.excluded_files = {'*.pyc', '*.pyo', '*.log', '*.tmp'}
        
    def get_source_files(self) -> List[Path]:
        """Recursively find all Python source files."""
        source_files = []
        for path in self.root_path.rglob('*.py'):
            # Check if any parent directory is excluded
            if any(part in self.excluded_dirs for part in path.parts):
                continue
            # Check if file name matches excluded patterns
            if any(path.name.endswith(ext) for ext in self.excluded_files):
                continue
            source_files.append(path)
        return sorted(source_files)
    
    def read_file(self, file_path: Path) -> str:
        """Read the content of a file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading {file_path}: {str(e)}"
    
    def get_file_hash(self, content: str) -> str:
        """Generate a SHA256 hash of the file content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def analyze_codebase(self) -> Dict[str, Any]:
        """Analyze the codebase structure and content."""
        files = self.get_source_files()
        analysis = {
            'total_files': len(files),
            'files': [],
            'total_lines': 0,
            'imports': set()
        }
        
        for file_path in files:
            content = self.read_file(file_path)
            lines = content.splitlines()
            analysis['total_lines'] += len(lines)
            
            # Extract imports (simple heuristic)
            for line in lines:
                line = line.strip()
                if line.startswith('import ') or line.startswith('from '):
                    analysis['imports'].add(line)
            
            analysis['files'].append({
                'path': str(file_path.relative_to(self.root_path)),
                'hash': self.get_file_hash(content),
                'lines': len(lines),
                'content': content
            })
        
        analysis['imports'] = list(analysis['imports'])
        return analysis

class EvolutionPlanner:
    """Generates evolution plans based on codebase analysis."""
    
    def __init__(self, inspector: CodebaseInspector):
        self.inspector = inspector
    
    def generate_plan(self, focus_area: Optional[str] = None) -> EvolutionPlan:
        """
        Generate an evolution plan.
        
        In a full implementation, this would call the AI engine to analyze
        the codebase and propose changes. For this foundational module,
        we provide a structured framework that can be extended.
        """
        step_id = f"evo_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        analysis = self.inspector.analyze_codebase()
        
        # Placeholder logic: In production, this calls the AI model
        # to analyze 'analysis' and return structured proposals.
        # For now, we return an empty plan with metadata.
        
        proposals = []
        
        # Example: If focus_area is specified, we could filter files
        if focus_area:
            # Logic to identify files related to focus_area
            pass
        
        return EvolutionPlan(
            step_id=step_id,
            timestamp=datetime.utcnow().isoformat(),
            proposals=proposals,
            summary=f"Evolution plan generated for {analysis['total_files']} files. Focus: {focus_area or 'general'}",
            confidence_score=0.0
        )
    
    def validate_proposal(self, proposal: EvolutionProposal) -> Tuple[bool, str]:
        """Validate a single proposal for safety and correctness."""
        # Check if file exists for modify/delete
        if proposal.action in ['modify', 'delete']:
            file_path = self.inspector.root_path / proposal.file_path
            if not file_path.exists():
                return False, f"File does not exist: {proposal.file_path}"
        
        # Check if new_content is provided for create/modify
        if proposal.action in ['create', 'modify']:
            if not proposal.new_content:
                return False, "New content is required for create/modify actions"
        
        # Basic syntax check for Python files
        if proposal.file_path.endswith('.py') and proposal.new_content:
            try:
                compile(proposal.new_content, proposal.file_path, 'exec')
            except SyntaxError as e:
                return False, f"Syntax error in proposed content: {str(e)}"
        
        return True, "Valid"

class EvolutionExecutor:
    """Executes validated evolution plans."""
    
    def __init__(self, inspector: CodebaseInspector, planner: EvolutionPlanner):
        self.inspector = inspector
        self.planner = planner
    
    def execute_plan(self, plan: EvolutionPlan, dry_run: bool = True) -> Dict[str, Any]:
        """
        Execute an evolution plan.
        
        Args:
            plan: The evolution plan to execute.
            dry_run: If True, only simulate the changes.
        
        Returns:
            A dictionary with execution results.
        """
        results = {
            'step_id': plan.step_id,
            'dry_run': dry_run,
            'executed': [],
            'failed': [],
            'skipped': []
        }
        
        for proposal in plan.proposals:
            # Validate proposal
            is_valid, message = self.planner.validate_proposal(proposal)
            if not is_valid:
                results['failed'].append({
                    'file': proposal.file_path,
                    'action': proposal.action,
                    'reason': message
                })
                continue
            
            if dry_run:
                results['executed'].append({
                    'file': proposal.file_path,
                    'action': proposal.action,
                    'status': 'simulated'
                })
            else:
                # Actual execution logic
                try:
                    self._apply_proposal(proposal)
                    results['executed'].append({
                        'file': proposal.file_path,
                        'action': proposal.action,
                        'status': 'applied'
                    })
                except Exception as e:
                    results['failed'].append({
                        'file': proposal.file_path,
                        'action': proposal.action,
                        'reason': str(e)
                    })
        
        return results
    
    def _apply_proposal(self, proposal: EvolutionProposal):
        """Apply a single proposal to the codebase."""
        file_path = self.inspector.root_path / proposal.file_path
        
        if proposal.action == 'create':
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(proposal.new_content)
        
        elif proposal.action == 'modify':
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(proposal.new_content)
        
        elif proposal.action == 'delete':
            if file_path.exists():
                file_path.unlink()

def evolve(focus_area: Optional[str] = None, dry_run: bool = True) -> Dict[str, Any]:
    """
    Main entry point for the /evolve command.
    
    Args:
        focus_area: Optional area of the codebase to focus on.
        dry_run: If True, only simulate changes.
    
    Returns:
        A dictionary with the evolution plan and execution results.
    """
    inspector = CodebaseInspector()
    planner = EvolutionPlanner(ins

import json
import logging
from typing import Optional, Dict, Any

from moroai.core.context import Context
from moroai.core.llm import LLMClient
from moroai.utils.errors import CommandError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are MOROAI's Evolution Engine. Your task is to analyze the user's intent and generate a structured proposal for a code change.

You must respond with a valid JSON object containing exactly these keys:
- "step_title": A concise title for the change (e.g., "Add Weather Tool").
- "target_file": The relative path to the file that needs to be modified or created (e.g., "src/tools/weather.py").
- "action": One of "create", "modify", or "delete".
- "description": A detailed description of the changes to be made, including specific functions, classes, or logic.

Do not include any text outside the JSON object.
"""

class EvolveCommand:
    """
    Handles the /evolve command.
    Accepts a user intent and generates a structured proposal for self-directed development.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def execute(self, context: Context, args: list) -> Dict[str, Any]:
        """
        Execute the evolve command.
        
        Args:
            context: The current execution context.
            args: List of arguments, where args[0] is the intent string.
            
        Returns:
            A dictionary containing the structured proposal.
        """
        if not args or not args[0]:
            raise CommandError("Usage: /evolve <intent>. Example: /evolve add a new tool for fetching news.")

        intent = " ".join(args)
        
        logger.info(f"Processing evolve intent: {intent}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Intent: {intent}"}
        ]

        try:
            response = await self.llm_client.generate(messages)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise CommandError(f"Failed to generate proposal: {str(e)}")

        # Parse the JSON response
        try:
            # Handle potential markdown code blocks in the response
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            proposal = json.loads(content)
            
            # Validate required fields
            required_fields = ["step_title", "target_file", "action", "description"]
            for field in required_fields:
                if field not in proposal:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate action
            if proposal["action"] not in ["create", "modify", "delete"]:
                raise ValueError(f"Invalid action: {proposal['action']}")

            logger.info(f"Generated proposal: {proposal['step_title']}")
            return proposal

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Raw response: {response}")
            raise CommandError("Failed to parse proposal. Please try rephrasing your intent.")
        except ValueError as e:
            logger.error(f"Invalid proposal structure: {e}")
            raise CommandError(f"Invalid proposal: {str(e)}")

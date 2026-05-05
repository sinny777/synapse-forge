#!/usr/bin/env python3
"""
ToolRouter Main Entry Point

This script serves as the unified CLI for the ToolRouter framework.
It allows executing individual phases and archiving results cleanly.
"""

import argparse
import asyncio
import logging
import sys

# Configure basic logging for the CLI
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("tool_router_cli")

def parse_args():
    parser = argparse.ArgumentParser(
        description="ToolRouter: RAG-for-Tools Agentic Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py generate    # Run Phase 1: Generate synthetic data from MCP tools
  python main.py train       # Run Phase 2: Fine-tune the embedding model
  python main.py run         # Run Phase 3: Start interactive agentic session
  python main.py archive     # Archive current artifacts to start fresh
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.required = True
    
    # Phase 1: Generate
    parser_generate = subparsers.add_parser(
        "generate", 
        help="Phase 1: Generate synthetic training data using Teacher LLM"
    )
    
    # Phase 2: Train
    parser_train = subparsers.add_parser(
        "train", 
        help="Phase 2: Fine-tune the embedding model using contrastive learning"
    )
    
    # Phase 3: Run
    parser_run = subparsers.add_parser(
        "run", 
        help="Phase 3: Run the interactive Agentic system"
    )
    
    # Archive
    parser_archive = subparsers.add_parser(
        "archive", 
        help="Archive current data, models, and logs into a timestamped results folder"
    )
    
    return parser.parse_args()

def run_generate():
    """Execute Phase 1"""
    try:
        from tool_router.generator import main as phase1_main
        asyncio.run(phase1_main())
    except ImportError as e:
        logger.error(f"Failed to import Phase 1 module: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Phase 1 execution failed: {e}")
        sys.exit(1)

def run_train():
    """Execute Phase 2"""
    try:
        from tool_router.trainer import main as phase2_main
        phase2_main()
    except ImportError as e:
        logger.error(f"Failed to import Phase 2 module: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Phase 2 execution failed: {e}")
        sys.exit(1)

def run_runtime():
    """Execute Phase 3"""
    try:
        from tool_router.runtime import main as phase3_main
        asyncio.run(phase3_main())
    except ImportError as e:
        logger.error(f"Failed to import Phase 3 module: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting interactive session.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Phase 3 execution failed: {e}")
        sys.exit(1)

def run_archive():
    """Execute Archive Results"""
    try:
        from tool_router.utils.archive import main as archive_main
        archive_main()
    except ImportError as e:
        logger.error(f"Failed to import archive script: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Archive execution failed: {e}")
        sys.exit(1)

def main():
    args = parse_args()
    
    if args.command == "generate":
        run_generate()
    elif args.command == "train":
        run_train()
    elif args.command == "run":
        run_runtime()
    elif args.command == "archive":
        run_archive()
    else:
        logger.error(f"Unknown command: {args.command}")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()

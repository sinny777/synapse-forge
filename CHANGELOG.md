# Changelog

All notable changes to the NeuralToolRouter project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial implementation of NeuralToolRouter framework
- Phase 1: Synthetic data generation with Teacher LLM
- Phase 2: PyTorch model fine-tuning with contrastive learning
- Phase 3: Runtime agentic loop with semantic routing
- LLM-generated hard negatives for improved training
- Hybrid retrieval (BM25 + Dense embeddings with RRF)
- IBM BeeAI multi-agent mediclaim processing example
- Predefined tools JSON for testing without MCP servers
- Comprehensive documentation and examples
- MCP client with fallback to predefined tools
- Configuration management system
- Logging and monitoring capabilities

### Fixed
- MCP async context manager handling
- Tool loading from predefined JSON files

### Documentation
- README.md with complete usage instructions
- Architecture documentation with Mermaid diagrams
- API documentation for all modules
- Contributing guidelines
- Example implementations

## [0.1.0] - 2024-12-XX

### Added
- Initial release of NeuralToolRouter
- Core framework implementation
- Three-phase architecture
- MCP integration support
- Example tools and configurations

---

## Version History

### Version 0.1.0 (Initial Release)
**Release Date:** TBD

**Highlights:**
- Complete end-to-end framework for neural tool routing
- Support for multiple LLM providers (OpenAI, Anthropic, Google)
- Flexible configuration system
- Comprehensive testing suite
- Production-ready examples

**Components:**
- `config.py`: Configuration management
- `mcp_client.py`: MCP server integration
- `phase1_generator.py`: Synthetic data generation
- `phase2_trainer.py`: Model training and fine-tuning
- `phase3_runtime.py`: Runtime execution engine

**Known Issues:**
- MCP stdio transport may hang on some systems (workaround: use predefined tools)
- Hard negative generation sometimes falls back to heuristics

**Future Enhancements:**
- Support for additional embedding models
- Enhanced caching mechanisms
- Real-time model updates
- Distributed training support
- Web UI for monitoring and management
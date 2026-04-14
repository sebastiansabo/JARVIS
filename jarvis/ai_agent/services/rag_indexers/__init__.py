"""
RAG Indexer Mixins

Domain-specific indexer groups extracted from RAGService.
Each mixin provides indexing methods for a domain area and relies on
RAGService providing self.db, self.config, self.logger, self._index_document,
self._enrich_with_claude, self._has_embeddings, etc. at runtime.
"""

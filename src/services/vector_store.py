from chromadb import Client, Settings # type: ignore
import chromadb # type: ignore
import hashlib
import re

class CodeVectorStore:
    def __init__(self):
        # Initialize ChromaDB with persistent storage
        self.client = Client(Settings(
            persist_directory="./.chromadb",
            anonymized_telemetry=False
        ))
        
        # Create or get our collection
        self.collection = self.client.get_or_create_collection(
            name="code_segments",
            metadata={"hnsw:space": "cosine"}
        )

    def _generate_id(self, content: str) -> str:
        """Generate a stable ID for a piece of content"""
        return hashlib.md5(content.encode()).hexdigest()

    def _split_into_chunks(self, content: str, chunk_size: int = 1000) -> list:
        """Split content into overlapping chunks"""
        chunks = []
        
        # Simpler chunking approach that doesn't rely on regex
        lines = content.split('\n')
        current_chunk = []
        current_size = 0
        
        for line in lines:
            line_size = len(line) + 1  # +1 for newline
            
            if current_size + line_size > chunk_size and current_chunk:
                # Join current chunk and add to chunks
                chunks.append('\n'.join(current_chunk))
                # Keep last few lines for overlap
                overlap_lines = current_chunk[-3:]  # Keep last 3 lines for context
                current_chunk = overlap_lines + [line]
                current_size = sum(len(l) + 1 for l in current_chunk)
            else:
                current_chunk.append(line)
                current_size += line_size
        
        # Add the last chunk if there's anything left
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        return chunks

    def add_file(self, file_path: str, content: str):
        """Add a file's content to the vector store"""
        # Remove existing entries for this file
        self.collection.delete(
            where={"file_path": file_path}
        )
        
        # Split content into chunks
        chunks = self._split_into_chunks(content)
        
        # Prepare documents for insertion
        ids = []
        documents = []
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            chunk_id = self._generate_id(f"{file_path}:{i}:{chunk}")
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "file_path": file_path,
                "chunk_index": i,
                "total_chunks": len(chunks)
            })
        
        # Add to collection
        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )

    def search(self, query: str, n_results: int = 5) -> list:
        """Search for relevant code segments"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        # Format results
        formatted_results = []
        for i, doc in enumerate(results['documents'][0]):
            metadata = results['metadatas'][0][i]
            formatted_results.append({
                'content': doc,
                'file_path': metadata['file_path'],
                'chunk_index': metadata['chunk_index'],
                'distance': results['distances'][0][i] if 'distances' in results else None
            })
        
        return formatted_results 
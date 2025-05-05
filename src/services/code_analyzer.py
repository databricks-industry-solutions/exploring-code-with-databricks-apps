from dataclasses import dataclass
from typing import List, Set, Dict, Optional
import re
import networkx as nx
from .vector_store import CodeVectorStore
from concurrent.futures import ThreadPoolExecutor
import threading

@dataclass
class Variable:
    name: str
    type: str
    is_pointer: bool
    upstream: Set[str]  # Names of variables this one depends on
    function_name: Optional[str]  # Which function this variable is declared in, if any

@dataclass
class Function:
    name: str
    variables: Dict[str, Variable]  # Map of variable name to Variable
    body: str

class CodeAnalyzer:
    def __init__(self, w):
        self.w = w
        self.dependency_graph = nx.DiGraph()
        self.current_file = None  # Add this to track current file
        self.parsed_files = {}    # Add this to store parsed results
        # Initialize the vector store
        self.vector_store = CodeVectorStore()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._vector_store_lock = threading.Lock()
        
    def read_file_contents(self, file_path: str) -> str:
        """Read contents of a single file from the volume"""
        try:
            print(f"Reading file: {file_path}")
            response = self.w.files.download(file_path=file_path)
            file_contents = response.contents.read()
            return file_contents.decode('utf-8')
        except Exception as e:
            raise Exception(f"Failed to read file contents: {str(e)}")

    def parse_c_file(self, file_path: str) -> Dict[str, Function]:
        """Parse C file and extract variable relationships"""
        # Check if we've already parsed this file
        if file_path in self.parsed_files:
            self.dependency_graph = self.parsed_files[file_path]['graph']
            return self.parsed_files[file_path]['functions']

        # Clear graph for new parse
        self.dependency_graph.clear()
        self.current_file = file_path
        
        content = self.read_file_contents(file_path)
        
        # Submit vector store update to run in background
        self.executor.submit(self._update_vector_store, file_path, content)
        
        # Continue with regular parsing
        content_no_comments = self.remove_comments(content)
        
        # Extract all functions
        functions: Dict[str, Function] = {}
        
        # Pattern for function definitions
        func_pattern = r'\b(?:static\s+)?([a-zA-Z_][a-zA-Z0-9_]*\s*\*?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)\s*{'
        
        for match in re.finditer(func_pattern, content_no_comments):
            try:
                # Extract function info
                func_name = match.group(2)
                
                # Find function body
                start_pos = match.end()
                brace_count = 1
                pos = start_pos
                
                while brace_count > 0 and pos < len(content_no_comments):
                    if content_no_comments[pos] == '{':
                        brace_count += 1
                    elif content_no_comments[pos] == '}':
                        brace_count -= 1
                    pos += 1
                
                body = content_no_comments[start_pos:pos-1]
                
                # Create function object
                func = Function(name=func_name, variables={}, body=body)
                
                # Find variable declarations in function body
                self.extract_variables(body, func)
                
                # Find variable dependencies in function body
                self.analyze_dependencies(body, func)
                
                functions[func_name] = func
                
            except Exception as e:
                continue
        
        # Store results before returning
        self.parsed_files[file_path] = {
            'graph': self.dependency_graph.copy(),
            'functions': functions.copy()
        }
        
        return functions

    def _update_vector_store(self, file_path: str, content: str):
        """Update vector store in background thread"""
        try:
            with self._vector_store_lock:
                self.vector_store.add_file(file_path, content)
        except Exception as e:
            print(f"Warning: Failed to add to vector store: {str(e)}")

    def remove_comments(self, content: str) -> str:
        """Remove C-style comments from the code"""
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Remove single-line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        return content

    def extract_variables(self, body: str, func: Function):
        """Extract variable declarations from function body"""
        # Updated pattern to catch more variable declarations
        var_pattern = r'\b(?:static\s+)?(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_]*(?:\s*\*)*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:[=;]|[\[{])'
        
        # Also look for function parameters
        param_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*(?:\s*\*)*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:,|\))'
        
        # Process regular variable declarations
        for match in re.finditer(var_pattern, body):
            type_name = match.group(1).strip()
            var_name = match.group(2)
            is_pointer = '*' in type_name
            type_name = type_name.replace('*', '').strip()
            
            var = Variable(
                name=var_name,
                type=type_name,
                is_pointer=is_pointer,
                upstream=set(),
                function_name=func.name
            )
            
            func.variables[var_name] = var
        
        # Process function parameters
        for match in re.finditer(param_pattern, body):
            type_name = match.group(1).strip()
            var_name = match.group(2)
            is_pointer = '*' in type_name
            type_name = type_name.replace('*', '').strip()
            
            var = Variable(
                name=var_name,
                type=type_name,
                is_pointer=is_pointer,
                upstream=set(),
                function_name=func.name
            )
            
            func.variables[var_name] = var

    def analyze_dependencies(self, body: str, func: Function):
        """Analyze variable dependencies within function body"""
        # First, add all variables to the graph with their attributes
        for var_name, var in func.variables.items():
            attrs = {
                'type': var.type,
                'is_pointer': var.is_pointer,
                'function': func.name
            }
            self.dependency_graph.add_node(var_name, **attrs)
            
            # Look for assignments to this variable
            assignment_pattern = fr'\b{var_name}\s*=\s*([^;]+);'
            
            for match in re.finditer(assignment_pattern, body):
                rhs = match.group(1)
                # Find all variables used in the right-hand side
                for other_var in func.variables:
                    if other_var != var_name and re.search(fr'\b{other_var}\b', rhs):
                        var.upstream.add(other_var)
                        # Add edge to dependency graph (other_var -> var_name)
                        self.dependency_graph.add_edge(other_var, var_name)
                
                # Also look for constants in the assignment
                constants = re.findall(r'\b\d+\b', rhs)
                for constant in constants:
                    constant_node = f"Constant: {constant}"
                    self.dependency_graph.add_node(constant_node, type="constant")
                    self.dependency_graph.add_edge(constant_node, var_name)

    def get_variable_dependencies(self, variable_name: str) -> nx.DiGraph:
        """Get a subgraph of dependencies for a specific variable"""
        if variable_name not in self.dependency_graph:
            return nx.DiGraph()
        
        # Get all predecessors (upstream dependencies)
        predecessors = nx.ancestors(self.dependency_graph, variable_name)
        predecessors.add(variable_name)
        
        # Create subgraph with the variable and its dependencies
        return self.dependency_graph.subgraph(predecessors)

    def get_all_variables(self) -> List[str]:
        """Get list of all variables in the codebase"""
        return [node for node in self.dependency_graph.nodes 
                if not str(node).startswith("Constant:")]

    def get_variable_info(self, variable_name: str) -> Dict:
        """Get detailed information about a variable"""
        matching_nodes = [
            node for node in self.dependency_graph.nodes 
            if node == variable_name
        ]
        
        if not matching_nodes:
            return {}
        
        node = matching_nodes[0]
        attrs = dict(self.dependency_graph.nodes[node])
        
        # Create subgraphs for upstream and downstream dependencies
        upstream = list(self.dependency_graph.predecessors(node))
        downstream = list(self.dependency_graph.successors(node))
        
        # Sort upstream dependencies by importance
        if upstream:
            upstream_subgraph = self.dependency_graph.subgraph(upstream)
            try:
                centrality = nx.eigenvector_centrality(upstream_subgraph)
            except:
                try:
                    centrality = nx.degree_centrality(upstream_subgraph)
                except:
                    centrality = {node: 1.0 for node in upstream_subgraph.nodes()}
            upstream = sorted(upstream, key=lambda x: centrality.get(x, 0), reverse=True)
        
        # Sort downstream dependencies by importance
        if downstream:
            downstream_subgraph = self.dependency_graph.subgraph(downstream)
            try:
                centrality = nx.eigenvector_centrality(downstream_subgraph)
            except:
                try:
                    centrality = nx.degree_centrality(downstream_subgraph)
                except:
                    centrality = {node: 1.0 for node in downstream_subgraph.nodes()}
            downstream = sorted(downstream, key=lambda x: centrality.get(x, 0), reverse=True)
        
        return {
            'name': node,
            'type': attrs.get('type'),
            'function': attrs.get('function'),
            'is_pointer': attrs.get('is_pointer'),
            'upstream': upstream,
            'downstream': downstream
        }

    def visualize_dependencies(self, variable_name: str, show_all: bool = False) -> nx.DiGraph:
        """Get a graph visualization for a variable's dependencies"""
        # Get the subgraph for the variable
        subgraph = self.get_variable_dependencies(variable_name)
        
        if show_all:
            # Return the full subgraph
            for node in subgraph.nodes:
                if str(node).startswith("Constant:"):
                    subgraph.nodes[node]['style'] = 'constant'
                else:
                    subgraph.nodes[node]['style'] = 'variable'
                    if node == variable_name:
                        subgraph.nodes[node]['style'] = 'target'
            return subgraph
        
        # Otherwise, show focused view with top 25 nodes
        try:
            centrality = nx.eigenvector_centrality(subgraph)
        except:
            try:
                centrality = nx.degree_centrality(subgraph)
            except:
                centrality = {node: 1.0 for node in subgraph.nodes()}

        top_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:25]
        related_items = [node[0] for node in top_nodes]

        subgraph_subset = subgraph.subgraph(related_items)
        
        for node in subgraph_subset.nodes:
            if str(node).startswith("Constant:"):
                subgraph_subset.nodes[node]['style'] = 'constant'
            else:
                subgraph_subset.nodes[node]['style'] = 'variable'
                if node == variable_name:
                    subgraph_subset.nodes[node]['style'] = 'target'
        
        return subgraph_subset

    def get_symbol_details(self, file_path, symbol_name=None):
        """
        Get focused details about a specific symbol or the currently selected symbol.
        Returns a SymbolInfo object with relevant details.
        """
        # Parse the file
        ast = self.parse_c_file(file_path)
        
        # Get symbol details
        symbol_info = SymbolInfo(
            name=symbol_name,
            type="variable/function/struct",
            dependencies=["list", "of", "dependencies"],
            used_by=["list", "of", "dependents"],
            function_name="containing_function"
        )
        
        return symbol_info

    def search_code(self, query: str, n_results: int = 5) -> list:
        """Search through parsed code using vector similarity"""
        try:
            with self._vector_store_lock:
                return self.vector_store.search(query, n_results)
        except Exception as e:
            print(f"Error searching code: {str(e)}")
            return []

    def __del__(self):
        """Cleanup thread pool on deletion"""
        self.executor.shutdown(wait=False)

class SymbolInfo:
    def __init__(self, name, type, dependencies, used_by, function_name):
        self.name = name
        self.type = type
        self.dependencies = dependencies
        self.used_by = used_by
        self.function_name = function_name
from dash import html, dcc
from databricks.sdk import WorkspaceClient
import dash_cytoscape as cyto
from .components.catalog_picker import CatalogPicker
from .components.chat_interface import ChatInterface
from .styles.catalog_picker import catalog_picker_styles
from .styles.chat_interface import chat_interface_styles
from .services.code_analyzer import CodeAnalyzer

class DatabricksChatbot:
    def __init__(self, app, endpoint_name, height='600px'):
        self.app = app
        self.height = height
        
        try:
            self.w = WorkspaceClient()
        except Exception as e:
            print(f'Error initializing WorkspaceClient: {str(e)}')
            self.w = None

        # Create single shared CodeAnalyzer instance
        self.code_analyzer = CodeAnalyzer(self.w)

        # Initialize components with shared analyzer
        self.catalog_picker = CatalogPicker(app, self.w, self.code_analyzer)
        self.chat_interface = ChatInterface(app, self.w, endpoint_name, self.code_analyzer)
        
        self.layout = self._create_layout()
        self._add_custom_css()

    def _create_layout(self):
        return html.Div([
            dcc.Store(id='code-context-store'),
            dcc.Store(id='chat-history-store'),
            dcc.Store(id='ast-store'),
            
            # Top row with file selection and variable explorer
            html.Div([
                # File selection on the left
                html.Div([
                    self.catalog_picker.create_layout(),
                ], className='col-3'),
                
                # Variable explorer on the right
                html.Div([
                    # Add Variable/Function Search Section (initially hidden)
                    html.Div([
                        html.Label('Search Variables', className='fw-bold mb-1'),
                        dcc.Dropdown(
                            id='symbol-search-dropdown',
                            options=[],
                            placeholder='Start typing to search...',
                            className='mb-3',
                            clearable=True,
                            searchable=True
                        ),
                        # Add details and graph container
                        html.Div([
                            # Variable details on the left
                            html.Div(
                                id='symbol-details',
                                className='mb-3 col-md-4'
                            ),
                            # Dependency graph on the right
                            html.Div([
                                cyto.Cytoscape(
                                    id='dependency-graph',
                                    layout={
                                        'name': 'breadthfirst',
                                        'rankDir': 'TB',
                                        'spacingFactor': 1.75,
                                        'animate': True
                                    },
                                    style={
                                        'width': '100%', 
                                        'height': '400px',
                                        'border': '1px solid #ddd',
                                        'borderRadius': '4px'
                                    },
                                    elements=[],
                                    stylesheet=[
                                        {
                                            'selector': 'node',
                                            'style': {
                                                'label': 'data(label)',
                                                'background-color': '#BFD7ED',
                                                'color': '#333',
                                                'font-size': '12px',
                                                'text-wrap': 'wrap',
                                                'text-max-width': '80px',
                                                'padding': '10px',
                                                'text-valign': 'center',
                                                'text-halign': 'center',
                                                'font-family': 'monospace'
                                            }
                                        },
                                        {
                                            'selector': 'node[type="constant"]',
                                            'style': {
                                                'background-color': '#98C1D9',
                                                'shape': 'round-rectangle',
                                                'font-size': '11px'
                                            }
                                        },
                                        {
                                            'selector': 'node[type="target"]',
                                            'style': {
                                                'background-color': '#3D5A80',
                                                'color': 'white',
                                                'font-weight': 'bold',
                                                'font-size': '14px'
                                            }
                                        },
                                        {
                                            'selector': 'edge',
                                            'style': {
                                                'width': 2,
                                                'line-color': '#666',
                                                'target-arrow-color': '#666',
                                                'target-arrow-shape': 'triangle',
                                                'curve-style': 'bezier',
                                                'arrow-scale': 1.5
                                            }
                                        }
                                    ]
                                )
                            ], className='col-md-8')
                        ], className='row')
                    ], id='symbol-search-container', style={'display': 'none'})
                ], className='col-9'),
            ], className='row mb-3'),
            
            # Add a spacer div to push chat interface to bottom
            html.Div(style={'height': '400px'}),  # Adjust height as needed
            
            # Bottom row with chat interface
            html.Div([
                html.Div([
                    self.chat_interface.create_chat_layout(),
                ], className='col-12'),
            ], className='row')
        ], className='container-fluid')

    def _add_custom_css(self):
        custom_css = f'''
            @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
            
            body {{
                font-family: 'DM Sans', sans-serif;
                background-color: #F9F7F4;
            }}
            
            /* Add styles for clickable symbols */
            .clickable-symbol {{
                color: #0066cc;
                text-decoration: none;
                cursor: pointer;
            }}
            
            .clickable-symbol:hover {{
                text-decoration: underline;
                opacity: 0.8;
            }}
            
            /* Markdown styling */
            .markdown-content pre {{
                background-color: #f8f9fa;
                padding: 8px;
                border-radius: 4px;
                margin: 8px 0;
                overflow-x: auto;
            }}
            
            .markdown-content code {{
                background-color: #f8f9fa;
                padding: 2px 4px;
                border-radius: 4px;
                font-family: monospace;
            }}
            
            .markdown-content p {{
                margin: 0;
            }}
            
            .markdown-content ul, .markdown-content ol {{
                margin: 8px 0;
                padding-left: 20px;
            }}
            
            {catalog_picker_styles}
            {chat_interface_styles}
        '''
        self.app.index_string = self.app.index_string.replace(
            '</head>',
            f'<style>{custom_css}</style></head>'
        )


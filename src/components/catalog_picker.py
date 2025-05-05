from dash import html, dcc, Input, Output, State, ALL, dash, callback_context
from databricks.sdk import WorkspaceClient
import dash_bootstrap_components as dbc
from ..services.code_analyzer import CodeAnalyzer
import dash_cytoscape as cyto
import os
import requests
from github import Github # type: ignore

class CatalogPicker:
    def __init__(self, app, workspace_client, code_analyzer):
        self.app = app
        self.w = workspace_client
        self.code_analyzer = code_analyzer
        self.default_catalog = os.getenv('default_catalog', 'default')
        self.default_schema = os.getenv('default_schema', 'default')
        self.default_volume = os.getenv('default_volume', 'default')
        self.default_file = os.getenv('default_file', '')
        self._create_callbacks()

    def create_layout(self):
        try:
            catalog_options = [
                {'label': catalog.name, 'value': catalog.name} 
                for catalog in self.w.catalogs.list()
            ]
        except Exception as e:
            print(f'Error fetching catalogs: {str(e)}')
            catalog_options = []

        return html.Div([
            # File selection components
            html.Label('Catalog', className='fw-bold mb-1'),
            dcc.Dropdown(
                id='catalog-dropdown',
                options=catalog_options,
                value=self.default_catalog,
                placeholder='Select a catalog...',
                className='mb-3'
            ),
            
            html.Label('Schema', className='fw-bold mb-1'),
            dcc.Dropdown(
                id='schema-dropdown',
                options=[],
                placeholder='Select a schema...',
                className='mb-3'
            ),
            
            html.Label('Volume', className='fw-bold mb-1'),
            dcc.Dropdown(
                id='volume-dropdown',
                options=[],
                placeholder='Select a volume...',
                className='mb-3'
            ),
            
            html.Label('File', className='fw-bold mb-1'),
            dcc.Dropdown(
                id='file-picker-dropdown',
                options=[],
                placeholder='Select a file...',
                className='mb-3'
            ),
            
            # Add download container with spinner and hidden button
            html.Div([
                html.Div([
                    dbc.Button(
                        "Download SQLite Example Files",
                        id='download-sqlite-files',
                        color='primary',
                        size='sm',
                        className='mt-2',
                        style={'display': 'none'}  # Hidden by default
                    ),
                ], id='download-files-container'),
                dbc.Spinner(
                    id='download-spinner',
                    color='primary',
                    spinner_style={'display': 'none'},
                ),
            ], className='d-flex align-items-center gap-2'),
            
            # Parse result and view toggle in a row
            html.Div([
                html.Div(
                    id='parse-result',
                    style={'display': 'inline-block', 'marginRight': '10px'}
                ),
                dbc.Button(
                    "Show All Dependencies",
                    id='toggle-view-button',
                    color='secondary',
                    size='sm',
                    style={'display': 'none'}
                )
            ], className='d-flex align-items-center')
        ], className='catalog-picker bg-white p-3 rounded shadow-sm')

    def _create_callbacks(self):
        @self.app.callback(
            Output('schema-dropdown', 'options'),
            Output('schema-dropdown', 'value'),
            Input('catalog-dropdown', 'value')
        )
        def update_schema_options(selected_catalog):
            if not selected_catalog:
                return [], None
            
            try:
                schemas = self.w.schemas.list(catalog_name=selected_catalog)
                schema_options = [
                    {'label': schema.name, 'value': schema.name}
                    for schema in schemas
                ]
                # Updated default schema logic
                default_schema = self.default_schema if selected_catalog == self.default_catalog else None
                return schema_options, default_schema
            except Exception as e:
                print(f'Error fetching schemas: {str(e)}')
                return [], None

        @self.app.callback(
            Output('volume-dropdown', 'options'),
            Output('volume-dropdown', 'value'),
            Input('schema-dropdown', 'value'),
            State('catalog-dropdown', 'value')
        )
        def update_volume_options(selected_schema, selected_catalog):
            if not selected_catalog or not selected_schema:
                return [], None
            
            try:
                volumes = self.w.volumes.list(
                    catalog_name=selected_catalog,
                    schema_name=selected_schema
                )
                volume_options = [
                    {'label': volume.name, 'value': volume.name}
                    for volume in volumes
                ]
                # Updated default volume logic
                default_volume = self.default_volume if (
                    selected_catalog == self.default_catalog and 
                    selected_schema == self.default_schema
                ) else None
                return volume_options, default_volume
            except Exception as e:
                print(f'Error fetching volumes: {str(e)}')
                return [], None

        @self.app.callback(
            Output('file-picker-dropdown', 'options'),
            Output('file-picker-dropdown', 'value'),
            Output('download-files-container', 'children'),
            Input('volume-dropdown', 'value'),
            State('catalog-dropdown', 'value'),
            State('schema-dropdown', 'value')
        )
        def update_file_options(selected_volume, selected_catalog, selected_schema):
            if not selected_catalog or not selected_schema or not selected_volume:
                return [], None, None
            
            try:
                volume_path = f'/Volumes/{selected_catalog}/{selected_schema}/{selected_volume}'
                files = self.w.files.list_directory_contents(volume_path)
                file_options = [
                    {'label': entry.path.split('/')[-1], 'value': entry.path}
                    for entry in files
                    if entry.path.endswith('.c')
                ]
                
                # Show download button if no C files found
                if not file_options:
                    download_button = dbc.Button(
                        "Download SQLite Example Files",
                        id='download-sqlite-files',
                        color='primary',
                        size='sm',
                        className='mt-2'
                    )
                    return [], None, download_button
                
                # Updated default file logic
                default_value = next(
                    (opt['value'] for opt in file_options 
                     if opt['label'] == self.default_file),
                    None
                ) if (
                    selected_catalog == self.default_catalog and 
                    selected_schema == self.default_schema and 
                    selected_volume == self.default_volume
                ) else None
                
                return file_options, default_value, None
            except Exception as e:
                print(f'Error fetching files: {str(e)}')
                return [], None, None

        @self.app.callback(
            Output('parse-result', 'children'),
            Output('symbol-search-dropdown', 'value', allow_duplicate=True),
            Input('file-picker-dropdown', 'value'),
            prevent_initial_call=True
        )
        def auto_parse_file(file_path):
            if not file_path:
                return '', None
            
            try:
                self.code_analyzer.parse_c_file(file_path)
                return html.Div('File parsed successfully!', 
                              style={'color': 'green', 'marginTop': '10px'}), None
            except Exception as e:
                error_message = str(e)
                if "Parse error near line" in error_message:
                    return html.Div([
                        html.Div('Parse error:', 
                                style={'color': 'red', 'marginTop': '10px', 'fontWeight': 'bold'}),
                        html.Pre(error_message,
                                style={'backgroundColor': '#f8f9fa', 
                                      'padding': '10px', 
                                      'borderRadius': '4px',
                                      'whiteSpace': 'pre-wrap',
                                      'fontFamily': 'monospace',
                                      'fontSize': '0.9em'})
                    ]), None
                else:
                    return html.Div([
                        html.Div('Error:', 
                                style={'color': 'red', 'marginTop': '10px', 'fontWeight': 'bold'}),
                        html.Pre(f"Error processing C file: {str(e)}",
                                style={'backgroundColor': '#f8f9fa', 
                                      'padding': '10px', 
                                      'borderRadius': '4px',
                                      'whiteSpace': 'pre-wrap',
                                      'fontFamily': 'monospace'})
                    ]), None

        @self.app.callback(
            Output('symbol-search-container', 'style'),
            Output('symbol-search-dropdown', 'options'),
            Input('parse-result', 'children')
        )
        def update_symbol_search(parse_result):
            if not parse_result or isinstance(parse_result, str):
                return {'display': 'none'}, []
            
            try:
                # Get all variables and functions
                variables = self.code_analyzer.get_all_variables()
                
                # Create options list with types
                options = []
                
                # Add variables
                for var in variables:
                    var_info = self.code_analyzer.get_variable_info(var)
                    if var_info:
                        # Format the label more cleanly
                        function_info = f" in {var_info['function']}" if var_info['function'] else " (global)"
                        label = html.Div([
                            html.Div([
                                html.Span(var, style={'font-weight': 'bold'}),
                                html.Span(function_info, style={'color': '#666', 'font-size': '0.9em'})
                            ]),
                            html.Div(
                                var_info['type'],
                                style={'color': '#0066cc', 'font-size': '0.8em'}
                            )
                        ])
                        
                        options.append({
                            'label': label,
                            'value': f"var::{var}",
                            'search': var
                        })
                
                # Sort options alphabetically by variable name
                options.sort(key=lambda x: x['value'])
                
                return {'display': 'block'}, options
            except Exception as e:
                print(f"Error updating symbol search: {str(e)}")
                return {'display': 'none'}, []

        @self.app.callback(
            Output('symbol-search-dropdown', 'value'),
            Output('dependency-graph', 'elements'),
            Output('symbol-details', 'children'),
            Input('symbol-search-dropdown', 'value'),
            Input('dependency-graph', 'tapNodeData'),
            Input('toggle-view-button', 'n_clicks'),
            Input({'type': 'var-link', 'name': ALL}, 'n_clicks'),
            State({'type': 'var-link', 'name': ALL}, 'id'),
            prevent_initial_call=True
        )
        def update_all_components(dropdown_value, tapped_node, n_clicks, link_clicks, link_ids):
            ctx = callback_context
            if not ctx.triggered:
                return dash.no_update, dash.no_update, dash.no_update
            
            trigger_id = ctx.triggered[0]['prop_id']
            
            # Determine the selected value based on the trigger
            if any(link_clicks):  # Check if any link was clicked
                clicked_idx = next((i for i, clicks in enumerate(link_clicks) if clicks), None)
                if clicked_idx is not None and clicked_idx < len(link_ids):
                    selected_value = f"var::{link_ids[clicked_idx]['name']}"
                    # Force update the dropdown value when a link is clicked
                    dropdown_value = selected_value
            elif '.tapNodeData' in trigger_id and tapped_node:
                selected_value = f"var::{tapped_node['id']}"
            else:
                selected_value = dropdown_value

            if not selected_value:
                return None, [], ''

            try:
                # Ensure consistent formatting
                if ':' in selected_value and not selected_value.startswith('var::'):
                    selected_value = 'var::' + selected_value.split(':')[-1]
                
                if not selected_value.startswith('var::'):
                    return selected_value, [], html.Div(f"Invalid selection format: {selected_value}")
                
                symbol_name = selected_value[5:]
                
                # Generate graph elements
                show_all = n_clicks and n_clicks % 2 == 1
                graph = self.code_analyzer.visualize_dependencies(symbol_name, show_all=show_all)
                elements = []
                
                # Add nodes
                for node in graph.nodes():
                    node_data = {
                        'data': {
                            'id': str(node),
                            'label': str(node),
                            'type': 'constant' if str(node).startswith('Constant:') 
                                    else 'target' if node == symbol_name 
                                    else 'variable'
                        }
                    }
                    elements.append(node_data)
                
                # Add edges
                for source, target in graph.edges():
                    edge_data = {
                        'data': {
                            'source': str(source),
                            'target': str(target)
                        }
                    }
                    elements.append(edge_data)
                
                # Generate symbol details
                var_info = self.code_analyzer.get_variable_info(symbol_name)
                if not var_info:
                    return selected_value, elements, html.Div(f"No information found for variable: {symbol_name}")
                
                # Create clickable links for upstream variables
                upstream_links = []
                if var_info.get('upstream'):
                    upstream_links = [
                        html.A(
                            name,
                            href='#',
                            id={'type': 'var-link', 'name': name},
                            className='clickable-symbol me-2',
                            n_clicks=0
                        ) if self.code_analyzer.get_variable_info(name) else html.Span(name)
                        for name in var_info['upstream']
                    ]
                
                # Create clickable links for downstream variables
                downstream_links = []
                if var_info.get('downstream'):
                    downstream_links = [
                        html.A(
                            name,
                            href='#',
                            id={'type': 'var-link', 'name': name},
                            className='clickable-symbol me-2',
                            n_clicks=0
                        ) if self.code_analyzer.get_variable_info(name) else html.Span(name)
                        for name in var_info['downstream']
                    ]

                details = html.Div([
                    html.H5(f"Variable: {symbol_name}"),
                    html.P([
                        html.Strong("Type: "), var_info.get('type', 'unknown'),
                        html.Br(),
                        html.Strong("Function: "), var_info.get('function', 'global'),
                        html.Br(),
                        html.Strong("Is Pointer: "), str(var_info.get('is_pointer', False)),
                    ]),
                    html.Div([
                        html.Strong("Upstream: "),
                        html.Div(
                            [item for pair in zip(upstream_links, [', '] * (len(upstream_links)-1) + ['']) 
                             for item in pair] if upstream_links else ['none'],
                            style={
                                'maxHeight': '100px',
                                'overflowY': 'auto',
                                'padding': '8px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '4px',
                                'marginTop': '4px',
                                'marginBottom': '8px'
                            }
                        ),
                        html.Strong("Downstream: "),
                        html.Div(
                            [item for pair in zip(downstream_links, [', '] * (len(downstream_links)-1) + ['']) 
                             for item in pair] if downstream_links else ['none'],
                            style={
                                'maxHeight': '100px',
                                'overflowY': 'auto',
                                'padding': '8px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '4px',
                                'marginTop': '4px'
                            }
                        )
                    ])
                ])
                
                return selected_value, elements, details
                
            except Exception as e:
                return selected_value, [], html.Div(f"Error: {str(e)}")

        # Add a new callback to handle variable link clicks
        @self.app.callback(
            Output('symbol-search-dropdown', 'value', allow_duplicate=True),
            Input({'type': 'var-link', 'name': ALL}, 'n_clicks'),
            State({'type': 'var-link', 'name': ALL}, 'id'),
            prevent_initial_call=True
        )
        def handle_var_link_click(n_clicks, ids):
            if not n_clicks or not ids:  # Add check for ids
                return dash.no_update
            
            try:
                # Find which link was clicked
                clicked_idx = next((i for i, clicks in enumerate(n_clicks) if clicks), None)
                if clicked_idx is None or clicked_idx >= len(ids):  # Add bounds check
                    return dash.no_update
                    
                var_name = ids[clicked_idx]['name']
                if not var_name:  # Add check for var_name
                    return dash.no_update
                    
                return f"var::{var_name}"
            except Exception as e:
                print(f"Error handling variable link click: {str(e)}")
                return dash.no_update

        @self.app.callback(
            Output('toggle-view-button', 'style'),
            Input('parse-result', 'children'),
            Input('symbol-search-dropdown', 'value')
        )
        def show_toggle_button(parse_result, selected_value):
            if not parse_result or isinstance(parse_result, str) or not selected_value:
                return {'display': 'none'}
            
            try:
                if selected_value.startswith('var::'):
                    symbol_type = 'var'
                    symbol_name = selected_value[5:]
                    graph = self.code_analyzer.get_variable_dependencies(symbol_name)
                    # Only show button if there are more than 25 nodes
                    if len(graph.nodes) > 25:
                        return {'display': 'inline-block'}
            except Exception as e:
                print(f"Error checking graph size: {str(e)}")
            
            return {'display': 'none'}

        @self.app.callback(
            Output('toggle-view-button', 'children'),
            Input('toggle-view-button', 'n_clicks')
        )
        def update_toggle_text(n_clicks):
            if n_clicks and n_clicks % 2 == 1:
                return "Show Focused View"
            return "Show All Dependencies"

        @self.app.callback(
            Output('parse-result', 'children', allow_duplicate=True),
            Output('file-picker-dropdown', 'options', allow_duplicate=True),
            Output('download-files-container', 'children', allow_duplicate=True),
            Input('download-sqlite-files', 'n_clicks'),
            State('catalog-dropdown', 'value'),
            State('schema-dropdown', 'value'),
            State('volume-dropdown', 'value'),
            prevent_initial_call=True
        )
        def download_sqlite_files(n_clicks, catalog, schema, volume):
            if not n_clicks:
                return dash.no_update, dash.no_update, dash.no_update
            
            try:
                volume_path = f'/Volumes/{catalog}/{schema}/{volume}'
                g = Github()
                repo = g.get_repo("sqlite/sqlite")
                contents = repo.get_contents("src")
                
                downloaded_files = []
                for content in contents:
                    if content.name in ['btree.c', 'btree.h']:
                        file_content = requests.get(content.download_url).text
                        file_path = f"{volume_path}/{content.name}"
                        self.w.files.upload(file_path, file_content.encode())
                        downloaded_files.append(content.name)
                
                # Get updated file list
                files = self.w.files.list_directory_contents(volume_path)
                file_options = [
                    {'label': entry.path.split('/')[-1], 'value': entry.path}
                    for entry in files
                    if entry.path.endswith('.c')
                ]
                
                return (
                    html.Div(
                        f"Successfully downloaded: {', '.join(downloaded_files)}",
                        style={'color': 'green', 'marginTop': '10px'}
                    ),
                    file_options,  # Update the file picker options
                    None  # Remove the download button
                )
            except Exception as e:
                return (
                    html.Div(
                        f"Error downloading files: {str(e)}",
                        style={'color': 'red', 'marginTop': '10px'}
                    ),
                    [],
                    None
                )

        @self.app.callback(
            Output('download-spinner', 'spinner_style'),
            Input('download-sqlite-files', 'n_clicks'),
            State('download-spinner', 'spinner_style'),
        )
        def toggle_spinner(n_clicks, current_style):
            if not n_clicks:
                return {'display': 'none'}
            
            ctx = callback_context
            if ctx.triggered:
                button_id = ctx.triggered[0]['prop_id'].split('.')[0]
                if button_id == 'download-sqlite-files':
                    return {'display': 'block'}
            
            return {'display': 'none'}

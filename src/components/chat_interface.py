from dash import html, dcc, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
from ..services.code_analyzer import CodeAnalyzer
import re

class ChatInterface:
    def __init__(self, app, workspace_client, endpoint_name, code_analyzer):
        self.app = app
        self.w = workspace_client
        self.endpoint_name = endpoint_name
        self.code_analyzer = code_analyzer
        self._create_callbacks()

    def _create_callbacks(self):
        # New callback for immediate message display
        @self.app.callback(
            Output('chat-history-store', 'data', allow_duplicate=True),
            Output('user-input', 'value', allow_duplicate=True),
            Input('send-button', 'n_clicks'),
            Input('user-input', 'n_submit'),
            State('user-input', 'value'),
            State('chat-history-store', 'data'),
            prevent_initial_call=True
        )
        def add_user_message(send_clicks, n_submit, user_input, chat_history):
            if not user_input:
                return chat_history or [], ''
            
            if not chat_history:
                chat_history = []
                
            chat_history.append({
                'role': 'user',
                'content': user_input
            })
            
            return chat_history, ''

        # Modified callback for AI response
        @self.app.callback(
            Output('chat-history-store', 'data', allow_duplicate=True),
            Input('chat-history-store', 'data'),
            State('file-picker-dropdown', 'value'),
            State('symbol-search-dropdown', 'value'),
            prevent_initial_call=True
        )
        def get_ai_response(chat_history, file_path, selected_symbol):
            if not chat_history or chat_history[-1]['role'] != 'user':
                return chat_history or []

            try:
                # Get the last user message
                last_message = chat_history[-1]['content']
                
                # Prepare focused context from the selected file and symbol
                code_context = ""
                
                # Add selected symbol context if available
                if file_path and selected_symbol:
                    try:
                        # Parse the symbol type and name
                        if '::' in selected_symbol:
                            symbol_type, symbol_name = selected_symbol.split('::', 1)
                            
                            if symbol_type == 'var' and symbol_name:
                                var_info = self.code_analyzer.get_variable_info(symbol_name)
                                
                                if var_info:
                                    # Limit to 10 most important dependencies
                                    upstream_details = []
                                    for up_var in var_info['upstream'][:10]:  # Limit to first 10
                                        up_info = self.code_analyzer.get_variable_info(up_var)
                                        if up_info:
                                            upstream_details.append(
                                                f"  - {up_var} ({up_info['type']}) in {up_info['function'] or 'global'}"
                                            )
                                
                                    downstream_details = []
                                    for down_var in var_info['downstream'][:10]:  # Limit to first 10
                                        down_info = self.code_analyzer.get_variable_info(down_var)
                                        if down_info:
                                            downstream_details.append(
                                                f"  - {down_var} ({down_info['type']}) in {down_info['function'] or 'global'}"
                                            )

                                    code_context += (
                                        f"Context about the code being discussed:\n"
                                        f"- File: {file_path}\n"
                                        f"- Variable: {symbol_name}\n"
                                        f"- Type: {var_info['type']}\n"
                                        f"- Scope: {var_info['function'] or 'global'}\n"
                                        f"- Is Pointer: {var_info['is_pointer']}\n"
                                        f"\nUpstream Dependencies:\n"
                                        + ('\n'.join(upstream_details) if upstream_details else "  - none")
                                        + f"\n\nDownstream Dependencies:\n"
                                        + ('\n'.join(downstream_details) if downstream_details else "  - none")
                                        + "\n\n---\nUser Question:\n"
                                    )
                    except Exception as e:
                        code_context = f"Note: Failed to get variable details: {str(e)}\n---\nUser Question:\n"
                
                # Add vector search results to context
                search_results = self.code_analyzer.search_code(last_message + code_context)
                if search_results:
                    code_context += "Relevant code segments:\n\n"
                    for result in search_results:
                        code_context += f"From {result['file_path']}:\n```c\n{result['content']}\n```\n\n"
                
                # Create a separate messages list for the API call
                api_messages = []
                
                # Add all previous messages from chat history except the last user message
                for msg in chat_history[:-1]:
                    api_messages.append(ChatMessage(
                        content=msg['content'],
                        role=ChatMessageRole[msg['role'].upper()]
                    ))
                
                # Add the last user message with context prepended
                final_message = code_context + last_message if code_context else last_message
                api_messages.append(ChatMessage(
                    content=final_message,
                    role=ChatMessageRole.USER
                ))
                
                # Get AI response
                response = self.w.serving_endpoints.query(
                    name=self.endpoint_name,
                    messages=api_messages,
                )
                
                # Add AI response to visible chat history
                chat_history.append({
                    'role': 'assistant',
                    'content': response.choices[0].message.content
                })
                
            except Exception as e:
                chat_history.append({
                    'role': 'assistant',
                    'content': f'Error: {str(e)}'
                })
            
            return chat_history

        def clean_message_content(content):
            # Use a loop to repeatedly remove content between tags
            while True:
                # Remove both tool_call and tool_call_result tags
                new_content = re.sub(r'<tool_call>[\s\S]*?</tool_call>|<tool_call_result>[\s\S]*?</tool_call_result>', '', content)
                if new_content == content:
                    # No more replacements to be made
                    break
                content = new_content
            return content.strip()

        @self.app.callback(
            Output('chat-history', 'children'),
            Input('chat-history-store', 'data')
        )
        def update_chat_display(chat_history):
            if not chat_history:
                return []
            
            chat_elements = []
            for message in chat_history:
                role = message['role']
                # Clean the content before displaying
                content = clean_message_content(message['content'])
                
                style = {
                    'padding': '10px',
                    'margin': '5px',
                    'border-radius': '10px',
                    'max-width': '70%',
                }
                
                if role == 'user':
                    style.update({
                        'background-color': '#DCF8C6',
                        'margin-left': 'auto',
                    })
                else:
                    style.update({
                        'background-color': '#E8E8E8',
                        'margin-right': 'auto',
                    })
                
                chat_elements.append(
                    html.Div([
                        dcc.Markdown(
                            content,
                            # Add these styles to properly format code blocks
                            style={'margin': '0'},
                            className='markdown-content'
                        )
                    ], style=style)
                )
            
            return chat_elements

        @self.app.callback(
            Output('symbol-search-dropdown', 'value', allow_duplicate=True),
            Input('dependency-graph', 'tapNodeData'),
            prevent_initial_call=True
        )
        def handle_node_click(node_data):
            if node_data:
                node_id = node_data.get('id')
                if node_id:
                    # Add the 'var:' prefix to match the symbol search format
                    return f'var:{node_id}'
            return None

        # Add callback to show/hide typing indicator
        @self.app.callback(
            Output('typing-container', 'style'),
            Input('chat-history-store', 'data'),
            prevent_initial_call=True
        )
        def toggle_typing_indicator(chat_history):
            if not chat_history:
                return {'display': 'none'}
            
            # Show typing indicator when last message is from user
            if chat_history and chat_history[-1]['role'] == 'user':
                return {
                    'display': 'block',
                    'margin-left': '10px',
                    'margin-bottom': '10px'
                }
            return {'display': 'none'}

        @self.app.callback(
            Output('chat-history-store', 'data', allow_duplicate=True),
            Input('clear-button', 'n_clicks'),
            prevent_initial_call=True
        )
        def clear_chat_history(n_clicks):
            if n_clicks:
                return []
            return no_update

    def create_chat_layout(self):
        return html.Div([
            html.Div(
                id='chat-history', 
                style={
                    'height': '300px',
                    'overflow-y': 'auto',
                    'border': '1px solid #ddd',
                    'border-radius': '4px 4px 0 0',
                    'margin-bottom': '0px',
                    'padding': '10px'
                }
            ),
            # Add typing indicator
            html.Div(
                html.Div(
                    "...",
                    className="typing-indicator"
                ),
                id="typing-container",
                style={'display': 'none'}  # Hidden by default
            ),
            dbc.Row([
                dbc.Col([
                    dbc.Input(
                        id='user-input',
                        type='text',
                        placeholder='Type your message...',
                        style={'width': '100%'}
                    ),
                ], width=10),
                dbc.Col([
                    dbc.Button('Send', id='send-button', color='primary', className='me-2'),
                    dbc.Button('Clear', id='clear-button', color='secondary')
                ], width=2)
            ], className='mt-0 p-2')
        ], className='bg-white rounded shadow-sm chat-container', style={
            'position': 'fixed',
            'bottom': '-10px',
            'left': '20px',
            'right': '20px',
            'z-index': '1000',
            'padding': '10px',
            'background': 'white',
            'box-shadow': '0 -2px 10px rgba(0,0,0,0.1)',
            'border-radius': '8px',
            'height': 'auto',
            'max-height': '400px'
        })



import os
import dash
from dash import html
import dash_bootstrap_components as dbc
from databricks.sdk import WorkspaceClient
from src.databricks_chatbot import DatabricksChatbot
from dotenv import load_dotenv

load_dotenv()

# Test serving endpoint
w = WorkspaceClient()
try:
    w.serving_endpoints.get(name=os.getenv("SERVING_ENDPOINT"))
except Exception as e:
    raise Exception(f"Error connecting to serving endpoint: {str(e)}")

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
server = app.server

# Initialize chatbot
chatbot = DatabricksChatbot(
    app=app,
    endpoint_name=os.getenv("SERVING_ENDPOINT")
)

# Set app layout
app.layout = html.Div([
    chatbot.layout
], className='container-fluid p-4')

if __name__ == '__main__':
    app.run_server(debug=True)

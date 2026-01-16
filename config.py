import os
from dotenv import load_dotenv
from google import genai

# Load the .env
load_dotenv()

# Extract specific variables
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Initialize global clients
client = genai.Client(api_key=GOOGLE_API_KEY)


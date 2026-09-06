import os
import re
from google import genai
from google.genai import types
from tools.code_search import search_code
from tools.database import inspect_database
from tools.file_reader import read_file
from tools.reproduction import run_reproduction
from tools.logs import read_logs
from tools.tests import execute_tests

# Initialize the Gemini Client
# Make sure GEMINI_API_KEY is set in your environment variables
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

AVAILABLE_TOOLS = {
    "search_code": search_code,
    "inspect_database": inspect_database,
    "read_file": read_file,
    "run_reproduction": run_reproduction,
    "read_logs": read_logs,
    "execute_tests": execute_tests
}

SYSTEM_PROMPT = """
You are a Incident Investigator operating in a strict loop of Reasoning and Acting.
You have access to the following tools:
-run_reproduction: Run a reproduction of a test case in the repository.
- read_file: Read the contents of a file in the repository.
- search_code: Search for code snippets in the repository.
- inspect_database: Inspect the database schema and contents.
- read_logs: Read the contents of log files.
- execute_tests: Execute tests in the repository.

Your responses must strictly follow this format:



... (User provides observation) ...
Thought: I have the calculation results.
Final Answer: The mass of Earth multiplied by 2 is 11.94 x 10^24 kg.
"""

def run_react_agent(user_query: str, max_iterations: int = 5):
    print(f"🚀 Starting Agent for query: '{user_query}'\n")
    
    # Initialize the memory/history with the system prompt and user query
    messages = [
        types.Content(role="user", parts=[types.Part.from_text(text=SYSTEM_PROMPT)]),
        types.Content(role="user", parts=[types.Part.from_text(text=user_query)])
    ]
    
    for i in range(max_iterations):
        # 1. Ask the LLM for its next step (Thought + Action or Final Answer)
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=messages
        )
        
        response_text = response.text
        print(response_text)
        
        # Keep tracking history
        messages.append(types.Content(role="model", parts=[types.Part.from_text(text=response_text)]))
        
        # 2. Check if the model gave a Final Answer
        if "Final Answer:" in response_text:
            print("\n✅ Task Complete!")
            return
            
        # 3. Parse Action if the model decides it needs a tool
        action_match = re.search(r"Action:\s*(\w+):\s*(.*)", response_text)
        if action_match:
            tool_name = action_match.group(1).strip()
            tool_input = action_match.group(2).strip()
            
            if tool_name in AVAILABLE_TOOLS:
                print(f"⚙️ [Executing Tool] Calling {tool_name} with input: '{tool_input}'")
                # Run the actual Python function
                observation = AVAILABLE_TOOLS[tool_name](tool_input)
                print(f"👁️ [Observation]: {observation}\n")
                
                # Append the observation back to the prompt history
                messages.append(types.Content(role="user", parts=[types.Part.from_text(text=f"Observation: {observation}")]))
            else:
                error_msg = f"Observation: Error - Tool '{tool_name}' does not exist."
                messages.append(types.Content(role="user", parts=[types.Part.from_text(text=error_msg)]))
        else:
            # Fallback if the model breaks formatting instructions
            print("\n⚠️ Format error. Forcing agent loop to close.")
            return

# Run the Agent
if __name__ == "__main__":
    query = "If I have an object with 3 times the mass of Mars, what is its weight in kg?"
    run_react_agent(query)

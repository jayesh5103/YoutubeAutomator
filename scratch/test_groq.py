import sys
sys.path.append('.')
from script_writer import _generate_with_groq

prompt = "Hello! Please return a JSON with a single key 'message' and value 'success'."
res = _generate_with_groq(prompt)
print("Result:")
print(res)

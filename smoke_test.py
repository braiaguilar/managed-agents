import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()  # toma ANTHROPIC_API_KEY del entorno

resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=100,
    messages=[{"role": "user", "content": "Decí 'setup ok' si me leés."}],
)
print(resp.usage)
print(resp.content[0].text)
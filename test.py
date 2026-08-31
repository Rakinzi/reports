from openai import OpenAI
import os

client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key="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",
)

stream = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-R1:fastest",
    messages=  [
        {
        "role": "user",
        "content": "What's today's date"
        }
    ], 
    stream=True
)


for event in stream:
    if not event.choices:
        continue
    delta = event.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)
print()
from langchain_groq import ChatGroq
import os 
llm = ChatGroq(
    model="qwen/qwen3-32b",
    temperature=0,
    max_tokens=1200,
    GROQ_API_KEY = os.getenv("GROQ_API_KEY"),
    timeout = 60
)
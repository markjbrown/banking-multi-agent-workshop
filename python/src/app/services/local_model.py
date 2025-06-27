from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model_name="lmstudio-community/qwen2.5-7b-instruct",
    openai_api_base="http://localhost:1234/",
    openai_api_key="lm-studio",
    temperature=0.3,
    max_tokens=1024,
)

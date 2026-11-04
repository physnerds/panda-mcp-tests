import os
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model=os.environ["BNL_MODEL"],
                 base_url = os.environ["BNL_BASE_URL"],
                 api_key = os.environ["BNL_API_KEY"],
                 stream_usage = False,
                 timeout = 120,
                 max_retries = 3)


response = llm.invoke(
    [
        ("system", "You are a scientific computing assistant."),
        ("human", "Explain the difference between a Slurm job and a job array."),
    ]
)

print(response.content)
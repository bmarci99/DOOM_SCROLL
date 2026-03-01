from src.paper_digest.main import run


if __name__ == '__main__':
    #KEYS = ["macro", "stress test", "SVAR", "LLM", "interpretability"]
    KEYS =[]


    run("config.yaml", keywords=KEYS)
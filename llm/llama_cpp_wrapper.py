# Wrapper Python per llama.cpp (TinyLlama)
# TODO: Implementazione streaming e gestione processi

class LlamaCppWrapper:
    def __init__(self, model_path, context_window=2048, max_tokens=128, timeout=20):
        self.model_path = model_path
        self.context_window = context_window
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(self, prompt, stream=False):
        """
        Esegue llama.cpp con il prompt fornito.
        Se stream=True, restituisce un generatore di token.
        """
        import subprocess
        import shlex
        llama_bin = "./llama.cpp/build/bin/llama-cli"
        cmd = [
            llama_bin,
            "-m", self.model_path,
            "-n", str(self.max_tokens),
            "-p", prompt,
            "--ctx-size", str(self.context_window),
        ]
        # Per output token-by-token
        if stream:
            cmd.append("--interactive")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            buffer = []
            for line in proc.stdout:
                # Filtra banner e prompt
                if line.strip() == "" or line.startswith("build") or line.startswith("model") or line.startswith("> "):
                    continue
                # Output token-by-token
                yield line.strip()
            proc.stdout.close()
            proc.wait(timeout=self.timeout)
        except Exception as e:
            yield f"[ERRORE llama.cpp] {e}"

if __name__ == "__main__":
    model_path = "models/tinyllama-1.1b-chat-v1.0-q4_K_M.gguf"
    llm = LlamaCppWrapper(model_path)
    while True:
        prompt = input("human: ")
        if prompt.strip().lower() in ("exit", "quit", "esci"): break
        print("Prompt:", prompt)
        for token in llm.generate(prompt):
            print("DELTA:", token)
